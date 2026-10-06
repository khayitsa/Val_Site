// --- extracted from <script> ---
var pieces = [
  { cat:'Fine Line',    title:'Botanical Bloom',   icon:'bloom',   img:'portfolio/botanical-bloom.jpg' },
  { cat:'Ornamental',   title:'Sun Mandala',        icon:'mandala', img:'portfolio/sun-mandala.jpg' },
  { cat:'Illustrative', title:'Evil Eye Talisman',  icon:'eye',     img:'portfolio/evil-eye-talisman.jpg' },
  { cat:'Fine Line',    title:'Celestial Arc',      icon:'arc',     img:'portfolio/celestial-arc.jpg' },
  { cat:'Geometric',    title:'Sacred Serpent',     icon:'serpent', img:'portfolio/sacred-serpent.jpg' },
  { cat:'Illustrative', title:'Wild Roses',         icon:'rose',    img:'portfolio/wild-roses.jpg' },
  { cat:'Calligraphy',  title:'Sacred Script',      icon:'script',  img:'portfolio/sacred-script.jpg' },
  { cat:'Ornamental',   title:'Golden scarab',      icon:'scarab',  img:'portfolio/golden-scarab.jpg' },
  { cat:'Fine Line',    title:'Lotus Rising',       icon:'lotus',   img:'portfolio/lotus-rising.jpg' }
];
document.addEventListener("DOMContentLoaded", function () {
  const burger = document.querySelector(".burger");
  const nav = document.querySelector(".navlinks");

  if (burger) {
    burger.addEventListener("click", () => {
      nav.classList.toggle("open");
    });
  }

  const form = document.querySelector("form");
  const note = document.querySelector(".form-note");

  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      note.textContent = "Message sent successfully.";
      note.classList.add("ok");
      form.reset();
    });
  }
});