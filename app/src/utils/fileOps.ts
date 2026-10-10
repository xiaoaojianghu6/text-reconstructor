import { open } from "@tauri-apps/plugin-dialog";
import { readTextFile, writeTextFile, readDir, mkdir } from "@tauri-apps/plugin-fs";

export { readTextFile, writeTextFile, readDir, mkdir };

export interface FileEntry {
  name: string;
  path: string;
  isDirectory: boolean;
}

export async function openSingleFile(): Promise<{
  path: string;
  content: string;
} | null> {
  const selected = await open({
    multiple: false,
    filters: [
      { name: "Text", extensions: ["txt", "md"] },
      { name: "All", extensions: ["*"] },
    ],
  });
  if (!selected) return null;
  const filePath = typeof selected === "string" ? selected : selected;
  const content = await readTextFile(filePath);
  return { path: filePath, content };
}

export async function openFolder(): Promise<{
  folderPath: string;
  files: FileEntry[];
} | null> {
  const selected = await open({ directory: true });
  if (!selected) return null;
  const folderPath = typeof selected === "string" ? selected : selected;
  return listFolder(folderPath);
}

export async function listFolder(folderPath: string): Promise<{
  folderPath: string;
  files: FileEntry[];
}> {
  const entries = await readDir(folderPath);
  const files: FileEntry[] = entries
    .filter((e) => !e.name.startsWith("."))
    .filter((e) => {
      if (e.isDirectory) return true;
      const ext = e.name.split(".").pop()?.toLowerCase();
      return ext === "md" || ext === "txt";
    })
    .map((e) => ({
      name: e.name,
      path: `${folderPath}/${e.name}`,
      isDirectory: e.isDirectory ?? false,
    }))
    .sort((a, b) => {
      if (a.isDirectory !== b.isDirectory) return a.isDirectory ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
  return { folderPath, files };
}

export async function createFileInFolder(
  folderPath: string,
  name: string,
): Promise<string> {
  const filePath = `${folderPath}/${name}`;
  await writeTextFile(filePath, `# ${name.replace(/\.md$/, "")}\n\n`);
  return filePath;
}
