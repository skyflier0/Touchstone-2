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
    if (!select) { return; }
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

function validateForm(event) {
  event.preventDefault();
  let ok = true;

  const name = document.getElementById("name");
  const nameErr = document.getElementById("name-error");
  if (name.value.trim() === "") {
    nameErr.textContent = "Please tell us your name.";
    ok = false;
  } else {
    nameErr.textContent = "";
  }

  const email = document.getElementById("email");
  const emailErr = document.getElementById("email-error");
  if (email.value.indexOf("@") === -1) {
    emailErr.textContent = "That email is missing an @ sign.";
    ok = false;
  } else {
    emailErr.textContent = "";
  }

  const status = document.getElementById("form-status");
  if (ok) {
    status.textContent = "Thanks, " + name.value + " — we will email you to confirm your spot.";
  } else {
    status.textContent = "";
  }
}
