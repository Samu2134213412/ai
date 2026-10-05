const q = new URLSearchParams(location.search);
const end = Date.now() + Number(q.get("left") || 0) * 1000;
const tick = () => {
  const left = Math.max(0, Math.round((end - Date.now()) / 1000));
  document.getElementById("t").textContent = TutorFocus.fmt(left);
  if (!left) document.querySelector("h1").textContent = "Fokus geschafft 🎉";
};
tick(); setInterval(tick, 1000);
document.getElementById("close").onclick = () => window.close();
