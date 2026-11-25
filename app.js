const sources = [
  {
    id: "los-sk",
    name: "LOS-SK",
    icon: "assets/icons/los-sk.svg",
    url: "https://los-sk.sk/index.php/competition/index",
  },
  {
    id: "squad",
    name: "SQUAD",
    icon: "assets/icons/squad.svg",
    url: "https://squad.sk/",
  },
  {
    id: "shootingarea",
    name: "Shooting Area",
    icon: "assets/icons/shootingarea.svg",
    url: "https://www.shootingarea.eu/sk/calendar-ipsc",
  },
  {
    id: "sads",
    name: "SADS",
    icon: "assets/icons/sads.svg",
    url: "https://new.sads.sk/index.php?option=com_kalendar&view=preteky&Itemid=414",
  },
  {
    id: "rda",
    name: "RDA IPSC",
    icon: "assets/icons/rda.svg",
    url: "https://match.rdaipsc.sk/",
  },
  {
    id: "szvvz",
    name: "SZVVZ",
    icon: "assets/icons/szvvz.svg",
    url: "https://www.szvvz.sk/kalendar/",
  },
];
const eventsElement = document.querySelector("#events");
const statusElement = document.querySelector("#status");
const sourceStatusElement = document.querySelector("#source-status");
const dateFiltersElement = document.querySelector("#date-filters");
const duplicateFiltersElement = document.querySelector("#duplicate-filters");
const feedbackButton = document.querySelector("#feedback-button");
const debugPreview =
  new URLSearchParams(window.location.search).get("debug") === "1" &&
  ["localhost", "127.0.0.1", "[::1]"].includes(window.location.hostname);
const dataDirectory = debugPreview ? "debug-data" : "data";
const enabledSources = new Map(sources.map((source) => [source.id, true]));
let selectedDateRange = "all";
let selectedDuplicateMode = "show";
let allEvents = [];
let duplicateThresholds;

if (debugPreview) {
  document.querySelector("#debug-banner").hidden = false;
}

feedbackButton.addEventListener("click", () => {
  const address = [
    118, 108, 97, 100, 105, 115, 108, 97, 118, 46, 122, 97, 108, 101, 115, 97,
    107, 64, 103, 109, 97, 105, 108, 46, 99, 111, 109,
  ]
    .map((character) => String.fromCharCode(character))
    .join("");
  window.location.href = `mailto:${address}`;
});

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;

  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];

    if (quoted) {
      if (character === '"' && text[index + 1] === '"') {
        field += '"';
        index += 1;
      } else if (character === '"') {
        quoted = false;
      } else {
        field += character;
      }
    } else if (character === '"' && field.length === 0) {
      quoted = true;
    } else if (character === ",") {
      row.push(field);
      field = "";
    } else if (character === "\n") {
      row.push(field.replace(/\r$/, ""));
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += character;
    }
  }

  if (quoted) {
    throw new Error("CSV obsahuje neukončenú úvodzovku.");
  }
  if (field.length > 0 || row.length > 0) {
    row.push(field.replace(/\r$/, ""));
    rows.push(row);
  }
  return rows;
}

async function loadEvents() {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const [thresholdResponse, loadedSources] = await Promise.all([
    fetch("duplicate-thresholds.json", { cache: "no-cache" }),
    Promise.all(
      sources.map(async (source) => {
        const manifestPath = `${dataDirectory}/${source.id}.json`;
        const manifestResponse = await fetch(manifestPath, { cache: "no-cache" });
        if (!manifestResponse.ok) {
          throw new Error(
            `Nepodarilo sa načítať ${manifestPath} (${manifestResponse.status}).`,
          );
        }
        const manifest = await manifestResponse.json();
        if (!manifest || manifest.source_id !== source.id) {
          throw new Error(`Neplatné údaje o zdroji ${source.name}.`);
        }
        if (
          manifest.file === null &&
          manifest.last_successful_at === null &&
          ["unknown", "failed"].includes(manifest.last_run_status)
        ) {
          return { source, manifest, events: [] };
        }

        const filenamePattern = new RegExp(
          `^${source.id}_\\d{8}T\\d{12}Z\\.csv$`,
        );
        if (
          typeof manifest.file !== "string" ||
          !filenamePattern.test(manifest.file) ||
          typeof manifest.last_successful_at !== "string" ||
          Number.isNaN(Date.parse(manifest.last_successful_at)) ||
          typeof manifest.last_attempted_at !== "string" ||
          Number.isNaN(Date.parse(manifest.last_attempted_at)) ||
          !["success", "failed"].includes(manifest.last_run_status)
        ) {
          throw new Error(`Neplatné údaje o aktualizácii zdroja ${source.name}.`);
        }

        const csvPath = `${dataDirectory}/${manifest.file}`;
        const response = await fetch(csvPath, { cache: "no-cache" });
        if (!response.ok) {
          throw new Error(`Nepodarilo sa načítať ${csvPath} (${response.status}).`);
        }
        return { source, manifest, text: await response.text() };
      }),
    ),
  ]);
  if (!thresholdResponse.ok) {
    throw new Error(
      `Nepodarilo sa načítať duplicate-thresholds.json (${thresholdResponse.status}).`,
    );
  }
  const thresholds = await thresholdResponse.json();
  if (
    !thresholds ||
    !Number.isFinite(thresholds.possible_threshold) ||
    !Number.isFinite(thresholds.strict_threshold) ||
    thresholds.possible_threshold < 0 ||
    thresholds.possible_threshold > 1 ||
    thresholds.strict_threshold < 0 ||
    thresholds.strict_threshold > 1 ||
    thresholds.strict_threshold < thresholds.possible_threshold
  ) {
    throw new Error("Neplatná konfigurácia prahov duplicít.");
  }

  const events = loadedSources.flatMap(({ source, text }) => {
    if (text === undefined) {
      return [];
    }
    const [header, ...rows] = parseCsv(text);
    if (!header) {
      return [];
    }
    const columns = Object.fromEntries(header.map((name, index) => [name, index]));
    for (const required of ["date", "location", "url"]) {
      if (columns[required] === undefined) {
        throw new Error(`V CSV chýba stĺpec "${required}".`);
      }
    }

    return rows
      .filter((row) => row.length > 1)
      .map((row) => ({
        date: row[columns.date],
        name: columns.name === undefined ? "" : row[columns.name] || "",
        location: row[columns.location],
        url: row[columns.url],
        type: columns.type === undefined ? "" : row[columns.type] || "",
        source,
      }))
      .filter((event) => {
        const date = new Date(`${event.date}T00:00:00`);
        return (
          !Number.isNaN(date.getTime()) &&
          date >= today &&
          event.location &&
          event.url
        );
      });
  });

  return { events, loadedSources, thresholds };
}

function renderSourceStatus(loadedSources) {
  sourceStatusElement.replaceChildren();
  const week = 7 * 24 * 60 * 60 * 1000;
  for (const { source, manifest } of loadedSources) {
    const item = document.createElement("article");
    item.setAttribute("role", "listitem");
    const details = document.createElement("div");
    const heading = document.createElement("div");
    const identity = document.createElement("div");
    const name = document.createElement("h3");
    const state = document.createElement("p");
    const icon = document.createElement("img");
    const actions = document.createElement("div");
    const toggleButton = document.createElement("button");
    const toggleTrack = document.createElement("span");
    const visibilityIcon = document.createElementNS(
      "http://www.w3.org/2000/svg",
      "svg",
    );
    const openEye = document.createElementNS(
      "http://www.w3.org/2000/svg",
      "g",
    );
    const openEyeOutline = document.createElementNS(
      "http://www.w3.org/2000/svg",
      "path",
    );
    const openEyePupil = document.createElementNS(
      "http://www.w3.org/2000/svg",
      "circle",
    );
    const closedEye = document.createElementNS(
      "http://www.w3.org/2000/svg",
      "g",
    );
    const sourceLink = document.createElement("a");
    const linkIcon = document.createElement("span");
    let status;
    if (
      manifest.last_run_status === "failed" &&
      manifest.file &&
      manifest.last_successful_at
    ) {
      status = "stale";
      state.textContent =
        "Posledný pokus zlyhal; zobrazujú sa posledné úspešné údaje";
    } else if (manifest.last_run_status === "failed") {
      status = "failed";
      state.textContent = "Posledný pokus zlyhal";
    } else if (!manifest.last_successful_at) {
      status = "unknown";
      state.textContent = "Zatiaľ bez úspešného scrape-u";
    } else if (Date.now() - Date.parse(manifest.last_successful_at) > week) {
      status = "stale";
      state.textContent = "Posledná úspešná aktualizácia je staršia ako týždeň";
    } else {
      status = "fresh";
      state.textContent = "Úspešne aktualizované";
    }

    item.className = `source-card source-card--${status}`;
    details.className = "source-card-details";
    heading.className = "source-card-heading";
    identity.className = "source-card-identity";
    name.className = "source-name";
    state.className = "source-state";
    icon.className = "source-icon";
    icon.src = source.icon;
    icon.alt = "";
    icon.loading = "lazy";
    icon.addEventListener("error", () => icon.remove());
    name.textContent = source.name;
    identity.append(icon, name);

    let isEnabled = enabledSources.get(source.id) !== false;
    actions.className = "source-card-actions";
    toggleButton.className = "source-toggle-button";
    toggleButton.type = "button";
    toggleButton.setAttribute("aria-pressed", String(isEnabled));
    toggleButton.setAttribute(
      "aria-label",
      `Zobrazovať súťaže zo zdroja ${source.name}`,
    );
    toggleTrack.className = "source-toggle-track";
    toggleTrack.setAttribute("aria-hidden", "true");
    visibilityIcon.classList.add("source-visibility-icon");
    visibilityIcon.setAttribute("viewBox", "0 0 24 24");
    visibilityIcon.setAttribute("aria-hidden", "true");
    visibilityIcon.setAttribute("fill", "none");
    visibilityIcon.setAttribute("stroke", "currentColor");
    visibilityIcon.setAttribute("stroke-width", "2");
    visibilityIcon.setAttribute("stroke-linecap", "round");
    visibilityIcon.setAttribute("stroke-linejoin", "round");
    openEye.classList.add("source-eye-open");
    openEyeOutline.setAttribute(
      "d",
      "M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7Z",
    );
    openEyePupil.setAttribute("cx", "12");
    openEyePupil.setAttribute("cy", "12");
    openEyePupil.setAttribute("r", "3");
    openEye.append(openEyeOutline, openEyePupil);
    closedEye.classList.add("source-eye-closed");
    for (const [tag, path] of [
      ["path", "M10.58 10.58a2 2 0 0 0 2.83 2.83"],
      ["path", "M16.68 16.68A10.7 10.7 0 0 1 12 18c-5 0-9-5-10-6 0 0 1.8-2.5 4-4.3"],
      ["path", "M9.88 5.09A10.8 10.8 0 0 1 12 5c5 0 9 5 10 7 0 0-.8 1.1-2.1 2.3"],
      ["path", "m2 2 20 20"],
    ]) {
      const element = document.createElementNS(
        "http://www.w3.org/2000/svg",
        tag,
      );
      element.setAttribute("d", path);
      closedEye.append(element);
    }
    visibilityIcon.append(openEye, closedEye);
    toggleButton.append(toggleTrack, visibilityIcon);
    toggleButton.addEventListener("click", () => {
      isEnabled = !isEnabled;
      enabledSources.set(source.id, isEnabled);
      toggleButton.setAttribute("aria-pressed", String(isEnabled));
      renderEventList();
    });

    sourceLink.className = "source-link-button";
    sourceLink.href = source.url;
    sourceLink.target = "_blank";
    sourceLink.rel = "noopener noreferrer";
    sourceLink.setAttribute("aria-label", `Otvoriť stránku ${source.name}`);
    sourceLink.title = `Otvoriť stránku ${source.name}`;
    linkIcon.className = "source-link-icon";
    linkIcon.setAttribute("aria-hidden", "true");
    linkIcon.textContent = "↗";
    const linkLabel = document.createElement("span");
    linkLabel.textContent = "Otvoriť";
    sourceLink.append(linkIcon, linkLabel);
    actions.append(toggleButton, sourceLink);
    heading.append(identity);
    details.append(heading, state);

    if (manifest.last_successful_at) {
      const lastSuccess = document.createElement("p");
      const time = document.createElement("time");
      time.dateTime = manifest.last_successful_at;
      time.textContent = new Intl.DateTimeFormat("sk-SK", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(manifest.last_successful_at));
      lastSuccess.className = "source-time";
      lastSuccess.append("Naposledy úspešne: ", time);
      details.append(lastSuccess);
    }

    if (manifest.last_run_status === "failed" && manifest.last_attempted_at) {
      const lastFailure = document.createElement("p");
      const time = document.createElement("time");
      time.dateTime = manifest.last_attempted_at;
      time.textContent = new Intl.DateTimeFormat("sk-SK", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(manifest.last_attempted_at));
      lastFailure.className = "source-time";
      lastFailure.append("Posledný pokus: ", time);
      details.append(lastFailure);
    }

    if (
      manifest.last_run_status === "failed" &&
      typeof manifest.last_error === "string" &&
      manifest.last_error
    ) {
      const errorMessage = document.createElement("p");
      errorMessage.className = "source-error";
      errorMessage.textContent = `Chyba: ${manifest.last_error}`;
      details.append(errorMessage);
    }

    item.append(details, actions);
    sourceStatusElement.append(item);
  }
}

const duplicateColorCount = 6;
const nameStopWords = new Set([
  "competition",
  "kolo",
  "match",
  "pretek",
  "preteky",
  "round",
]);
const locationStopWords = new Set([
  "range",
  "shooting",
  "slovakia",
  "slovensko",
  "strelnica",
]);

function eventDateKey(value) {
  const text = String(value ?? "").trim();
  const iso = text.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
  const local = text.match(/^(\d{1,2})\s*[./]\s*(\d{1,2})\s*[./]\s*(\d{4})$/);
  const parts = iso
    ? [Number(iso[1]), Number(iso[2]), Number(iso[3])]
    : local
      ? [Number(local[3]), Number(local[2]), Number(local[1])]
      : null;

  if (!parts) {
    return null;
  }

  const [year, month, day] = parts;
  const check = new Date(Date.UTC(year, month - 1, day));
  if (
    check.getUTCFullYear() !== year ||
    check.getUTCMonth() !== month - 1 ||
    check.getUTCDate() !== day
  ) {
    return null;
  }

  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function eventTokens(value, stopWords, year) {
  return new Set(
    String(value ?? "")
      .replace(/([a-z])([A-Z])/g, "$1 $2")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, " ")
      .trim()
      .split(/\s+/)
      .filter((token) => token && token !== String(year) && !stopWords.has(token)),
  );
}

function diceSimilarity(left, right) {
  if (left.size === 0 || right.size === 0) {
    return null;
  }

  let sharedTokens = 0;
  for (const token of left) {
    if (right.has(token)) {
      sharedTokens += 1;
    }
  }
  return (2 * sharedTokens) / (left.size + right.size);
}

function eventNameForMatching(event) {
  const name = String(event.name ?? "").trim();
  if (name) {
    return name;
  }

  const path = new URL(event.url, window.location.href).pathname;
  const slug = path.split("/").filter(Boolean).pop() || "";
  if (!slug || /^\d+$/.test(slug) || /^index(?:\.php)?$/i.test(slug)) {
    return "";
  }
  return decodeURIComponent(slug).replace(/[-_]+/g, " ");
}

function duplicateProbability(left, right) {
  const leftDate = eventDateKey(left.date);
  const rightDate = eventDateKey(right.date);
  if (leftDate && rightDate && leftDate !== rightDate) {
    return 0.02;
  }

  const year = Number((leftDate || rightDate || "").slice(0, 4)) || null;
  const nameScore = diceSimilarity(
    eventTokens(eventNameForMatching(left), nameStopWords, year),
    eventTokens(eventNameForMatching(right), nameStopWords, year),
  );
  const locationScore = diceSimilarity(
    eventTokens(left.location, locationStopWords),
    eventTokens(right.location, locationStopWords),
  );

  if (nameScore === null && locationScore === null) {
    return 0;
  }

  const parts = [
    [nameScore, 0.55],
    [locationScore, 0.3],
    [leftDate && rightDate ? 1 : null, 0.15],
  ].filter(([score]) => score !== null);
  const totalWeight = parts.reduce((sum, [, weight]) => sum + weight, 0);
  let score =
    parts.reduce((sum, [value, weight]) => sum + value * weight, 0) /
    totalWeight;

  if (!leftDate || !rightDate) {
    score = Math.min(score, 0.85);
  }
  if (nameScore === null) {
    score = Math.min(score, 0.75);
  }
  if (locationScore === null) {
    score = Math.min(score, 0.85);
  }

  return Math.round(score * 100) / 100;
}

function findDuplicateGroups(events, threshold) {
  const eventsByDate = new Map();
  for (const event of events) {
    const date = eventDateKey(event.date);
    if (!date) {
      continue;
    }
    if (!eventsByDate.has(date)) {
      eventsByDate.set(date, []);
    }
    eventsByDate.get(date).push(event);
  }

  const duplicateGroups = [];
  for (const sameDayEvents of eventsByDate.values()) {
    const groups = [];
    for (const event of sameDayEvents) {
      let bestMatch = null;
      for (const group of groups) {
        if (
          group.events.some(
            (member) => member.source.id === event.source.id,
          )
        ) {
          continue;
        }

        const scores = group.events.map((member) =>
          duplicateProbability(event, member),
        );
        if (scores.some((score) => score < threshold)) {
          continue;
        }

        const confidence = Math.min(group.confidence, ...scores);
        if (!bestMatch || confidence > bestMatch.confidence) {
          bestMatch = { group, confidence };
        }
      }

      if (bestMatch) {
        bestMatch.group.events.push(event);
        bestMatch.group.confidence = bestMatch.confidence;
      } else {
        groups.push({ events: [event], confidence: 1 });
      }
    }

    duplicateGroups.push(...groups.filter((group) => group.events.length > 1));
  }

  return duplicateGroups;
}

function chooseDuplicateRepresentative(group) {
  return group.events.reduce((best, candidate) => {
    const informationScore = (event) =>
      Number(Boolean(event.name.trim())) * 1000 +
      event.name.trim().length +
      event.location.trim().length;
    return informationScore(candidate) > informationScore(best)
      ? candidate
      : best;
  });
}

function chooseCompetitionType(events) {
  const types = [...new Set(events.map((event) => event.type.trim()).filter(Boolean))];
  if (types.includes("Steel Cup/Challenge")) {
    return "Steel Cup/Challenge";
  }
  if (types.includes("IPSC Action Air")) {
    return "IPSC Action Air";
  }
  if (types.includes("IPSC Rifle/Mini Rifle")) {
    return "IPSC Rifle/Mini Rifle";
  }
  if (types.length === 1) {
    return types[0];
  }
  if (types.length === 2 && types.includes("IPSC")) {
    return types.find((type) => type !== "IPSC");
  }
  return "";
}

function renderEventList() {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const endOfRange = new Date(today);
  endOfRange.setDate(endOfRange.getDate() + 30);

  let events = allEvents.filter((event) => {
    if (enabledSources.get(event.source.id) === false) {
      return false;
    }

    const eventDate = new Date(`${event.date}T00:00:00`);
    if (selectedDateRange === "year") {
      return eventDate.getFullYear() === today.getFullYear();
    }
    if (selectedDateRange === "30-days") {
      return eventDate >= today && eventDate < endOfRange;
    }
    return true;
  });

  events.sort((left, right) =>
    (eventDateKey(left.date) || "").localeCompare(eventDateKey(right.date) || ""),
  );
  const duplicateInfo = new Map();
  let duplicateGroups = [];
  if (selectedDuplicateMode !== "none") {
    const threshold =
      selectedDuplicateMode === "hide"
        ? duplicateThresholds.strict_threshold
        : duplicateThresholds.possible_threshold;
    duplicateGroups = findDuplicateGroups(events, threshold);
    duplicateGroups.forEach((group, index) => {
      const info = {
        id: index + 1,
        confidence: group.confidence,
        events: group.events,
        representative: chooseDuplicateRepresentative(group),
      };
      group.events.forEach((event) => duplicateInfo.set(event, info));
    });
  }
  eventsElement.replaceChildren();

  if (events.length === 0) {
    statusElement.textContent =
      [...enabledSources.values()].some(Boolean)
        ? "Pre vybrané filtre nie sú naplánované žiadne nadchádzajúce súťaže."
        : "Vyberte aspoň jeden zdroj súťaží.";
    return;
  }

  const renderedGroups = [];
  const renderedDuplicateGroups = new Set();
  for (const event of events) {
    const duplicate = duplicateInfo.get(event);
    if (!duplicate) {
      renderedGroups.push({ event, members: [event], duplicate: null });
    } else if (!renderedDuplicateGroups.has(duplicate)) {
      renderedDuplicateGroups.add(duplicate);
      renderedGroups.push({
        event: duplicate.representative,
        members: duplicate.events,
        duplicate,
      });
    }
  }

  const rows = renderedGroups.map(({ event, members, duplicate }) => {
    const row = document.createElement("tr");
    const dateCell = document.createElement("td");
    const nameCell = document.createElement("td");
    const typeCell = document.createElement("td");
    const locationCell = document.createElement("td");
    const sourcesCell = document.createElement("td");
    const sourceLinks = document.createElement("div");
    dateCell.dataset.label = "Dátum";
    nameCell.dataset.label = "Názov";
    dateCell.className = "competition-date-cell";
    typeCell.dataset.label = "Typ súťaže";
    typeCell.className = "competition-type-cell";
    locationCell.dataset.label = "Miesto";
    sourcesCell.className = "source-cell";
    sourcesCell.dataset.label = "Zdroje";
    sourceLinks.className = "event-source-links";
    dateCell.textContent = new Intl.DateTimeFormat("sk-SK", {
      dateStyle: "medium",
      timeZone: "UTC",
    }).format(new Date(`${event.date}T00:00:00Z`));
    nameCell.textContent = event.name;
    if (duplicate) {
      const badge = document.createElement("span");
      const sourceCount = members.length;
      const sourceLabel =
        sourceCount === 2 ? "2 zdroje" : `${sourceCount} zdrojov`;
      const confidenceLabel =
        selectedDuplicateMode === "show"
          ? ` · zhoda ${Math.round(duplicate.confidence * 100)} %`
          : "";
      const colorIndex = ((duplicate.id - 1) % duplicateColorCount) + 1;
      badge.className = `duplicate-badge duplicate-badge--color-${colorIndex}`;
      badge.textContent = `${sourceLabel}${confidenceLabel}`;
      nameCell.append(" ", badge);
    }
    typeCell.textContent = chooseCompetitionType(members);
    locationCell.textContent = event.location;

    for (const member of members) {
      const url = new URL(member.url, window.location.href);
      if (url.protocol !== "https:" && url.protocol !== "http:") {
        throw new Error("Odkaz na súťaž musí používať HTTP alebo HTTPS.");
      }
      const link = document.createElement("a");
      const icon = document.createElement("img");
      link.className = "event-source-link";
      link.href = url.href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.setAttribute(
        "aria-label",
        `Otvoriť detail preteku na stránke ${member.source.name}`,
      );
      link.title = `Detail na stránke ${member.source.name}`;
      icon.className = "source-icon";
      icon.src = member.source.icon;
      icon.alt = "";
      icon.loading = "lazy";
      icon.addEventListener("error", () => icon.remove());
      link.append(icon, member.source.name);
      sourceLinks.append(link);
    }
    sourcesCell.append(sourceLinks);
    row.append(dateCell, nameCell, typeCell, locationCell, sourcesCell);
    return row;
  });

  eventsElement.append(...rows);
  if (selectedDuplicateMode === "show") {
    statusElement.textContent = duplicateGroups.length
      ? `Zoskupené možné duplicity: ${duplicateGroups.length}.`
      : "V aktuálnych údajoch sa nenašli možné duplicity.";
  } else if (selectedDuplicateMode === "hide") {
    statusElement.textContent = duplicateGroups.length
      ? `Zoskupené duplicity s mierou zhody aspoň ${Math.round(duplicateThresholds.strict_threshold * 100)} %: ${duplicateGroups.length}.`
      : `Nenašli sa duplicity s mierou zhody aspoň ${Math.round(duplicateThresholds.strict_threshold * 100)} %.`;
  } else {
    statusElement.textContent = "";
  }
}

dateFiltersElement.addEventListener("click", (event) => {
  if (!(event.target instanceof Element)) {
    return;
  }
  const button = event.target.closest("button[data-range]");
  if (!button) {
    return;
  }
  selectedDateRange = button.dataset.range;
  for (const filterButton of dateFiltersElement.querySelectorAll("button[data-range]")) {
    filterButton.setAttribute(
      "aria-pressed",
      String(filterButton === button),
    );
  }
  renderEventList();
});

duplicateFiltersElement.addEventListener("click", (event) => {
  if (!(event.target instanceof Element)) {
    return;
  }
  const button = event.target.closest("button[data-mode]");
  if (!button) {
    return;
  }
  selectedDuplicateMode = button.dataset.mode;
  for (const filterButton of duplicateFiltersElement.querySelectorAll("button[data-mode]")) {
    filterButton.setAttribute(
      "aria-pressed",
      String(filterButton === button),
    );
  }
  renderEventList();
});

function renderEvents({ events, loadedSources, thresholds }) {
  allEvents = events;
  duplicateThresholds = thresholds;
  duplicateFiltersElement.querySelector('[data-mode="show"]').textContent =
    `Možné (${Math.round(thresholds.possible_threshold * 100)} %+)`;
  duplicateFiltersElement.querySelector('[data-mode="hide"]').textContent =
    `Iba isté (${Math.round(thresholds.strict_threshold * 100)} %+)`;
  renderSourceStatus(loadedSources);
  renderEventList();
}

loadEvents()
  .then(renderEvents)
  .catch((error) => {
    statusElement.textContent = "Súťaže sa nepodarilo načítať. Skúste to neskôr.";
    console.error(error);
  });
