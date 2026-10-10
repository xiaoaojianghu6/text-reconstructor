"""CLI 入口 -- 全链路文本重构"""

from __future__ import annotations

import logging
import sys

import click

from text_reconstructor.processor.chunker import SentenceSplitter
from text_reconstructor.processor.tagger import Tagger
from text_reconstructor.graph.updater import GraphUpdater
from text_reconstructor.output.llm_refiner import LLMRefiner
from text_reconstructor.output.text_output import TextOutput
from text_reconstructor.output.suggestions import Suggestions
from text_reconstructor.llm import LLMConfig

logger = logging.getLogger(__name__)


def _make_config(backend: str, api_key: str, **overrides) -> LLMConfig:
    """根据 backend 自动填充默认配置"""
    if backend == "ollama":
        kwargs = dict(backend="ollama", model="qwen3.5:0.8b", base_url="http://localhost:11434")
        kwargs.update(overrides)
        return LLMConfig(**kwargs)
    if backend == "nvidia":
        kwargs = dict(
            backend="nvidia",
            model="deepseek-ai/deepseek-v4-flash",
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=api_key or "",
            timeout=300.0,
        )
        kwargs.update(overrides)
        return LLMConfig(**kwargs)
    if backend == "deepseek":
        kwargs = dict(
            backend="deepseek",
            model="deepseek-chat",
            base_url="https://api.deepseek.com/v1",
            api_key=api_key or "",
            timeout=300.0,
        )
        kwargs.update(overrides)
        return LLMConfig(**kwargs)
    return LLMConfig()


@click.group()
def cli():
    pass


@cli.command()
@click.argument("text", required=False)
@click.option("--file", "-f", type=click.Path(exists=True), help="从文件读取输入")
@click.option(
    "--mode",
    type=click.Choice(["vpga", "auto"]),
    default="vpga",
    help="处理模式: vpga(VPGA全局重写,默认) / auto(旧管线)",
)
@click.option("--skip-adversary", is_flag=True, help="跳过对抗机验证(仅auto模式)")
@click.option(
    "--output-format", "--format",
    type=click.Choice(["auto", "template"]),
    default="auto",
    help="输出格式: auto(LLM重构,默认) / template(模板式,仅auto模式)",
)
@click.option(
    "--backend",
    type=click.Choice(["nvidia", "deepseek", "ollama"]),
    default="nvidia",
    help="LLM 后端: nvidia(云端,默认) / deepseek(DeepSeek官网) / ollama(本地)",
)
@click.option("--api-key", envvar="NVIDIA_NIM_API_KEY", default="", help="API Key (NVIDIA或DeepSeek)")
@click.option("--no-streaming", is_flag=True, help="禁用 Mini-Batch 流式标注，使用全量 Batch")
def main(text, file, mode, skip_adversary, output_format, backend, api_key, no_streaming):
    """文本重构工具 -- 将混乱长段文本转化为清晰的结构化输出"""
    content = _read_input(text, file)
    if not content or not content.strip():
        click.echo("错误: 输入为空", err=True)
        sys.exit(1)

    if mode == "vpga":
        _run_vpga(content, backend, api_key)
    else:
        _run_pipeline(content, backend, api_key, skip_adversary, output_format, no_streaming)


def _run_vpga(content: str, backend: str, api_key: str):
    """VPGA 模式: 直接全文重写"""
    from text_reconstructor.output.vpga_refiner import VPGARefiner

    config = _make_config(backend, api_key, max_tokens=8192, temperature=0.15)
    refiner = VPGARefiner(config=config)
    text_out = refiner.refine(content)
    click.echo(text_out)

    from text_reconstructor.output.detail_anchor import extract_from_sentences
    from text_reconstructor.processor.chunker import SentenceSplitter
    from text_reconstructor.output.fcr import compute_fcr

    splitter = SentenceSplitter()
    sentences = splitter.split(content)
    anchors = extract_from_sentences(sentences)
    if anchors:
        fcr_result = compute_fcr(sentences, text_out, anchors)
        if fcr_result["missing"]:
            logger.warning(
                "FCR 验证发现丢失实体 (%d/%d): %s",
                fcr_result["preserved"], fcr_result["total"],
                fcr_result["missing"],
            )


def _run_pipeline(content: str, backend: str, api_key: str,
                  skip_adversary: bool, output_format: str, no_streaming: bool):
    """旧管线模式: Tagger -> Graph -> Refiner"""
    splitter = SentenceSplitter()
    sentences = splitter.split(content)
    if not sentences:
        click.echo("错误: 未能从输入中分割出有效句子", err=True)
        sys.exit(1)

    tagger_config = _make_config(
        backend, api_key,
        max_tokens=512, temperature=0.1,
    )
    tagger = Tagger(config=tagger_config, override_with_rules=False)
    try:
        if no_streaming:
            chunks = tagger.batch_tag(sentences)
        else:
            chunks, _ = tagger.batch_tag_streaming(sentences)
    except Exception as e:
        click.echo(f"标注失败: {e}", err=True)
        sys.exit(1)

    if not chunks:
        click.echo("错误: 标注结果为空", err=True)
        sys.exit(1)

    adversary_config = _make_config(
        backend, api_key,
        max_tokens=256, temperature=0.1, timeout=60.0,
    )
    updater = GraphUpdater(
        run_adversary=not skip_adversary,
        llm_config=adversary_config,
    )
    try:
        snapshot = updater.process(chunks)
    except Exception as e:
        click.echo(f"图谱构建失败: {e}", err=True)
        sys.exit(1)

    if not snapshot.get("nodes"):
        click.echo("错误: 处理结果为空", err=True)
        sys.exit(1)

    if output_format == "template":
        text_out = TextOutput().format(snapshot)
    else:
        refiner_config = _make_config(
            backend, api_key,
            max_tokens=4096, temperature=0.15,
        )
        text_out = LLMRefiner(config=refiner_config).refine(snapshot)

        from text_reconstructor.output.detail_anchor import extract_from_sentences
        from text_reconstructor.output.fcr import compute_fcr
        anchors = extract_from_sentences(sentences)
        if anchors:
            fcr_result = compute_fcr(sentences, text_out, anchors)
            if fcr_result["missing"]:
                logger.warning(
                    "FCR 验证发现丢失实体 (%d/%d): %s",
                    fcr_result["preserved"], fcr_result["total"],
                    fcr_result["missing"],
                )
    click.echo(text_out)

    alerts = snapshot.get("alerts", [])
    if alerts:
        suggestions = Suggestions().format(alerts)
        click.echo("", err=True)
        click.echo("-- 改进建议 --", err=True)
        for s in suggestions:
            click.echo(s, err=True)


@cli.command()
@click.option(
    "--backend",
    type=click.Choice(["nvidia", "deepseek", "ollama"]),
    default="nvidia",
    help="评估使用的 LLM 后端",
)
@click.option("--api-key", envvar="NVIDIA_NIM_API_KEY", default="", help="API Key (NVIDIA或DeepSeek)")
@click.option("--output-report", type=click.Path(), default=None, help="报告输出路径")
@click.option(
    "--mode",
    type=click.Choice(["vpga", "pipeline"]),
    default="vpga",
    help="评估模式: vpga(VPGA全局重写,默认) / pipeline(旧管线)",
)
def evaluate(backend, api_key, output_report, mode):
    """运行对比评估 -- 基线 vs 系统"""
    from text_reconstructor.evaluation import Evaluator, ReportGenerator

    config = _make_config(backend, api_key, timeout=300.0)

    click.echo(f"正在运行评估 (mode={mode})...", err=True)
    evaluator = Evaluator(cloud_config=config)
    generator = ReportGenerator(evaluator, mode=mode)
    report = generator.generate()
    path = generator.save(report, output_report)
    click.echo(f"评估报告已保存: {path}", err=True)


def _read_input(text: str | None, file: str | None) -> str:
    """从参数、文件或 stdin 读取输入"""
    if file:
        with open(file, "r", encoding="utf-8") as f:
            return f.read()
    if text is not None:
        return text
    return click.get_text_stream("stdin").read()
