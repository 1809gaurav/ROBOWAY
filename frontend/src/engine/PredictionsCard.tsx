import { useEffect, useState } from "react";
import { API_BASE } from "./config";

export default function PredictionsCard() {
  const [enabled, setEnabled] = useState(false);
  const [prediction, setPrediction] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    let active = true;
    let timer: number | undefined;
    const check = async () => {
      try {
        const status = await fetch(`${API_BASE}/api/ml/status`).then((response) => response.json());
        if (!active) return;
        setEnabled(Boolean(status.enabled));
        if (!status.enabled) return;
        const result = await fetch(`${API_BASE}/api/ml/predict`, { method: "POST" }).then((response) => response.json());
        if (active && result.ok) setPrediction(result.prediction);
      } catch {
        if (active) setEnabled(false);
      }
      if (active) timer = window.setTimeout(check, 3000);
    };
    void check();
    return () => { active = false; if (timer) window.clearTimeout(timer); };
  }, []);

  if (!enabled) return null;
  return (
    <section className="panel-card">
      <div className="panel-title"><h3>Predictions</h3></div>
      <p><small>model output</small></p>
      <pre>{JSON.stringify(prediction ?? {}, null, 2)}</pre>
    </section>
  );
}
