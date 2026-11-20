console.log("script loaded");

const classes = [
  { id: "gentle",     name: "Gentle",            when: "foundation class" },
  { id: "vinyasa",    name: "Vinyasa",           when: "flow class"       },
  { id: "restorative",name: "Restorative",       when: "slow class"       },
  { id: "private",    name: "Private Sessions",  when: "one-on-one"       }
];

function buildOptions() {
  const select = document.getElementById("fav-select");
  for (const c of classes) {
    const opt = document.createElement("option");
    opt.value = c.id;
    opt.textContent = c.name + " (" + c.when + ")";
    select.appendChild(opt);
  }
}

function showFavorite() {
  const saved = localStorage.getItem("riverbend-fav");
  const msg = document.getElementById("fav-message");
  if (!msg) { return; }
  if (saved) {
    const found = classes.find(function (c) { return c.id === saved; });
    if (found) { msg.textContent = "Your favorite: " + found.name + " — see you there!"; }
  } else {
    msg.textContent = "";
  }
}

function saveFavorite() {
  const select = document.getElementById("fav-select");
  localStorage.setItem("riverbend-fav", select.value);
  showFavorite();
}

document.addEventListener("DOMContentLoaded", function () {
  buildOptions();
  showFavorite();
  const select = document.getElementById("fav-select");
  if (select) {
    select.addEventListener("change", showFavorite);
    document.getElementById("save-fav").addEventListener("click", saveFavorite);
  }
});
