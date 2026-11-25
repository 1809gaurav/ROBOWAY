import { useEffect, useState } from "react";
import QRCode from "qrcode";
import { Copy, X } from "lucide-react";

export default function MonitorShareModal({ apiBase, onClose }) {
  const [qrCode, setQrCode] = useState("");
  const [copyStatus, setCopyStatus] = useState("");
  const link = `${window.location.origin}/monitor?api=${encodeURIComponent(apiBase)}`;
  const localOrigin = ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);

  useEffect(() => {
    let active = true;
    QRCode.toDataURL(link, { width: 240, margin: 2, errorCorrectionLevel: "M" })
      .then((dataUrl) => { if (active) setQrCode(dataUrl); })
      .catch((error) => console.error("Could not create the phone monitor QR code.", error));
    return () => { active = false; };
  }, [link]);

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(link);
      setCopyStatus("Link copied");
    } catch (error) {
      console.error("Could not copy the phone monitor link.", error);
      setCopyStatus("Copy failed — select and copy the link above");
    }
  };

  return (
    <div className="monitor-share-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="monitor-share-dialog" role="dialog" aria-modal="true" aria-labelledby="monitor-share-title">
        <button className="monitor-share-close" onClick={onClose} aria-label="Close dialog"><X size={20} /></button>
        <h2 id="monitor-share-title">Monitor on phone</h2>
        <p>Scan this code to open a live, read-only view of your simulation.</p>
        <div className="monitor-qr">{qrCode ? <img src={qrCode} alt="QR code for the RoboWay phone monitor" /> : <span>Creating QR code…</span>}</div>
        <label htmlFor="monitor-share-link">Phone monitor link</label>
        <div className="monitor-share-link-row">
          <input id="monitor-share-link" readOnly value={link} onFocus={(event) => event.target.select()} />
          <button onClick={() => void copyLink()} aria-label="Copy phone monitor link"><Copy size={17} /> Copy</button>
        </div>
        <span className="monitor-copy-status" aria-live="polite">{copyStatus}</span>
        {localOrigin && <p className="monitor-local-warning">Open this from your laptop&apos;s network IP (e.g. http://192.168.x.x:5173) so the phone can reach it.</p>}
      </section>
    </div>
  );
}
