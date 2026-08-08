const root = document.documentElement;
const body = document.body;
const weightControl = document.querySelector("#weightControl");
const weightOutput = document.querySelector("#weightOutput");
const sweepControl = document.querySelector("#sweepControl");
const fontStatus = document.querySelector("#fontStatus");
const familyButtons = [...document.querySelectorAll("[data-family]")];
const featureButtons = [...document.querySelectorAll("[data-feature]")];
const singleLineEditors = [
  ...document.querySelectorAll('[contenteditable="plaintext-only"][aria-multiline="false"]'),
];

const families = {
  filled: "Monaco GP Sans",
  outline: "Monaco GP Sans Outline",
};

const activeFeatures = new Set();
let sweepFrame;
let sweepStarted;
const sweepDuration = 5200;

function setWeight(value) {
  const weight = Math.max(100, Math.min(900, Math.round(Number(value))));
  root.style.setProperty("--weight", String(weight));
  weightControl.value = String(weight);
  weightOutput.value = String(weight);
  weightOutput.textContent = String(weight);
}

function setFamily(key) {
  const selected = Object.hasOwn(families, key) ? key : "filled";
  root.style.setProperty("--family", `"${families[selected]}"`);
  body.dataset.family = selected;
  for (const button of familyButtons) {
    button.setAttribute("aria-pressed", String(button.dataset.family === selected));
  }
}

function setFeatures() {
  const value = [...activeFeatures]
    .sort()
    .map((tag) => `"${tag}" 1`)
    .join(", ");
  root.style.setProperty("--feature-settings", value || "normal");
  for (const button of featureButtons) {
    button.setAttribute("aria-pressed", String(activeFeatures.has(button.dataset.feature)));
  }
}

function stopSweep() {
  if (sweepFrame !== undefined) cancelAnimationFrame(sweepFrame);
  sweepFrame = undefined;
  sweepStarted = undefined;
  sweepControl.setAttribute("aria-pressed", "false");
  sweepControl.textContent = "Sweep weight";
}

function sweep(timestamp) {
  if (sweepStarted === undefined) sweepStarted = timestamp;
  const phase = ((timestamp - sweepStarted) % sweepDuration) / sweepDuration;
  const triangle = phase < 0.5 ? phase * 2 : (1 - phase) * 2;
  setWeight(100 + triangle * 800);
  sweepFrame = requestAnimationFrame(sweep);
}

weightControl.addEventListener("input", () => {
  stopSweep();
  setWeight(weightControl.value);
});

sweepControl.addEventListener("click", () => {
  if (sweepFrame !== undefined) {
    stopSweep();
    return;
  }
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
    setWeight(weightControl.value === "900" ? 100 : 900);
    return;
  }
  sweepControl.setAttribute("aria-pressed", "true");
  sweepControl.textContent = "Stop sweep";
  sweepFrame = requestAnimationFrame(sweep);
});

for (const button of familyButtons) {
  button.addEventListener("click", () => setFamily(button.dataset.family));
}

for (const button of featureButtons) {
  button.addEventListener("click", () => {
    const tag = button.dataset.feature;
    if (activeFeatures.has(tag)) activeFeatures.delete(tag);
    else activeFeatures.add(tag);
    setFeatures();
  });
}

for (const editor of singleLineEditors) {
  editor.addEventListener("keydown", (event) => {
    if (event.key === "Enter") event.preventDefault();
  });
  editor.addEventListener("beforeinput", (event) => {
    if (["insertLineBreak", "insertParagraph"].includes(event.inputType)) {
      event.preventDefault();
    }
  });
}

async function validateFontLoading() {
  const samples = [
    [families.filled, "MONACO VITESSE ÀÇŒ 01369"],
    [families.outline, "MONACO VITESSE ÀÇŒ 01369"],
  ];
  const weights = [100, 400, 900];

  try {
    await Promise.all(
      samples.flatMap(([family, text]) =>
        weights.map((weight) => document.fonts.load(`${weight} 64px "${family}"`, text)),
      ),
    );
    await document.fonts.ready;
    const checks = samples.flatMap(([family, text]) =>
      weights.map((weight) => ({
        family,
        weight,
        loaded: document.fonts.check(`${weight} 64px "${family}"`, text),
      })),
    );
    const failed = checks.filter((check) => !check.loaded);
    if (failed.length) throw new Error(`Font checks failed: ${JSON.stringify(failed)}`);

    const fontResources = performance
      .getEntriesByType("resource")
      .map((entry) => entry.name)
      .filter((url) => url.endsWith(".woff2"));
    const expectedFiles = ["MonacoGPSans%5Bwght%5D.woff2", "MonacoGPSansOutline%5Bwght%5D.woff2"];
    for (const filename of expectedFiles) {
      const decodedFilename = decodeURIComponent(filename);
      if (!fontResources.some((url) => decodeURIComponent(url).endsWith(decodedFilename))) {
        throw new Error(`Expected webfont resource was not requested: ${decodedFilename}`);
      }
    }

    fontStatus.dataset.state = "ready";
    fontStatus.textContent = "Filled + Outline loaded / Latin-only release";
    body.dataset.fontReady = "true";
    window.monacoGPSansSpecimenReady = {
      ready: true,
      checks,
      fontResources,
      weights,
      families: Object.values(families),
    };
  } catch (error) {
    fontStatus.dataset.state = "error";
    fontStatus.textContent = "Font load failed — see console";
    body.dataset.fontReady = "false";
    window.monacoGPSansSpecimenReady = { ready: false, error: error.message };
    console.error(error);
  }
}

setWeight(weightControl.value);
setFamily("filled");
setFeatures();
validateFontLoading();
