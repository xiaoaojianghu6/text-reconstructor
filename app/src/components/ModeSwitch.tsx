import "./ModeSwitch.css";

interface Props {
  mode: "writer" | "developer";
  onChange: (mode: "writer" | "developer") => void;
}

export default function ModeSwitch({ mode, onChange }: Props) {
  return (
    <div className="mode-switch">
      <button
        className={`mode-btn ${mode === "writer" ? "active" : ""}`}
        onClick={() => onChange("writer")}
      >
        作家模式
      </button>
      <button
        className={`mode-btn ${mode === "developer" ? "active" : ""}`}
        onClick={() => onChange("developer")}
      >
        开发者模式
      </button>
    </div>
  );
}
