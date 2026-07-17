import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";
const saved=localStorage.getItem("tricoach-theme");document.documentElement.dataset.theme=saved==="dark"||saved==="light"?saved:window.matchMedia?.("(prefers-color-scheme: dark)").matches?"dark":"light";
createRoot(document.getElementById("root")!).render(<StrictMode><App/></StrictMode>);
