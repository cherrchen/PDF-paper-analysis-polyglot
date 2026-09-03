import { workspaceLabel } from "@paper/ui";

const status = document.querySelector("#status");
if (status) {
  status.textContent = `${workspaceLabel()} workspace is running.`;
}
