// Stromverbrauch und Kompatibilitätsprüfung für einen Build.
// build = { cpu, mobo, ram, gpu, cooler, psu, case, storage: [] }

const BASE_WATT = 50; // Mainboard, Lüfter, USB, Verluste

export function powerDraw(build) {
  let w = BASE_WATT;
  const parts = [];
  const add = (label, watt) => { if (watt) { w += watt; parts.push({ label, watt }); } };
  add("Prozessor", build.cpu?.tdp);
  add("Grafikkarte", build.gpu?.tdp);
  add("Arbeitsspeicher", build.ram?.watt);
  add("CPU-Kühler", build.cooler?.watt);
  for (const s of build.storage) add(s.name, s.watt);
  parts.unshift({ label: "Mainboard, Lüfter, Rest", watt: BASE_WATT });
  return { total: w, parts };
}

// Empfohlene Netzteilleistung: 30 % Reserve für Lastspitzen, gerundet auf 50 W.
export function recommendedPsu(total) {
  return Math.ceil((total * 1.3) / 50) * 50;
}

// Liefert eine Liste von { level: "error" | "warn" | "ok", text }.
export function checkBuild(build) {
  const out = [];
  const err = (text) => out.push({ level: "error", text });
  const warn = (text) => out.push({ level: "warn", text });
  const ok = (text) => out.push({ level: "ok", text });
  const { cpu, mobo, ram, gpu, cooler, psu, storage } = build;
  const pcCase = build.case;

  if (cpu && mobo && (cpu.socket === "?" || mobo.socket === "?")) {
    warn("CPU-Sockel unbekannt – bitte selbst prüfen");
  } else if (cpu && mobo) {
    cpu.socket === mobo.socket
      ? ok(`CPU-Sockel passt (${cpu.socket})`)
      : err(`CPU-Sockel ${cpu.socket} passt nicht zum Mainboard (${mobo.socket})`);
  }
  if (ram && mobo) {
    ram.memType === mobo.memType
      ? ok(`RAM-Typ passt (${ram.memType})`)
      : err(`${ram.memType}-RAM passt nicht ins Mainboard (${mobo.memType})`);
    if (ram.sticks > mobo.ramSlots) err(`${ram.sticks} RAM-Riegel, aber nur ${mobo.ramSlots} Slots`);
  }
  if (mobo && pcCase) {
    pcCase.formFactors.includes(mobo.formFactor)
      ? ok(`Mainboard (${mobo.formFactor}) passt ins Gehäuse`)
      : err(`${mobo.formFactor}-Mainboard passt nicht ins Gehäuse (${pcCase.formFactors.join("/")})`);
  }
  // Bei importierten Gehäusen sind die Maße aus dem Gehäusetyp geschätzt – dann nur warnen.
  const sizeIssue = pcCase?.estimated ? (t) => warn(`${t} (Gehäusemaße geschätzt, bitte prüfen)`) : err;
  if (gpu && pcCase) {
    gpu.lengthMm <= pcCase.maxGpuMm
      ? ok(`Grafikkarte passt ins Gehäuse (${gpu.lengthMm} ≤ ${pcCase.maxGpuMm} mm)`)
      : sizeIssue(`Grafikkarte evtl. zu lang: ${gpu.lengthMm} mm, Gehäuse ca. ${pcCase.maxGpuMm} mm`);
  }
  if (cooler && cpu) {
    if (cooler.sockets && !cooler.sockets.includes(cpu.socket)) err(`Kühler unterstützt Sockel ${cpu.socket} nicht`);
    if (cooler.maxTdp < cpu.tdp) warn(`Kühler (bis ${cooler.maxTdp} W) ist knapp für die CPU (${cpu.tdp} W)`);
    else ok("Kühler schafft die CPU-Abwärme");
  }
  if (cooler && pcCase && cooler.heightMm != null && cooler.heightMm > pcCase.maxCoolerMm) {
    sizeIssue(`Kühler zu hoch: ${cooler.heightMm} mm, Gehäuse erlaubt ${pcCase.maxCoolerMm} mm`);
  }
  if (mobo) {
    const m2 = storage.filter((s) => s.kind === "m2").length;
    if (m2 > mobo.m2Slots) err(`${m2} M.2-SSDs, aber nur ${mobo.m2Slots} M.2-Slots`);
  }
  if (cpu && !gpu && !cpu.igpu) err("CPU hat keine integrierte Grafik – Grafikkarte nötig");

  const { total } = powerDraw(build);
  if (psu) {
    const rec = recommendedPsu(total);
    if (psu.watt < total) err(`Netzteil zu schwach: ${psu.watt} W < ${total} W Verbrauch`);
    else if (psu.watt < rec) warn(`Netzteil knapp: ${psu.watt} W, empfohlen ${rec} W`);
    else ok(`Netzteil reicht (${psu.watt} W, Auslastung ${Math.round((total / psu.watt) * 100)} %)`);
  }

  const missing = [];
  if (!cpu) missing.push("Prozessor");
  if (!mobo) missing.push("Mainboard");
  if (!ram) missing.push("RAM");
  if (!storage.length) missing.push("Speicher");
  if (!psu) missing.push("Netzteil");
  if (!pcCase) missing.push("Gehäuse");
  if (cpu && !cooler) missing.push("CPU-Kühler");
  if (missing.length) warn(`Fehlt noch: ${missing.join(", ")}`);

  return out;
}

// Ist ein Teil mit dem aktuellen Build verträglich? Für den Katalogfilter.
export function fitsBuild(part, build) {
  const trial = { ...build, storage: [...build.storage] };
  if (part.cat === "storage") trial.storage.push(part);
  else trial[part.cat] = part;
  return errorCount(trial) <= errorCount(build);
}

const errorCount = (b) => checkBuild(b).filter((r) => r.level === "error").length;
