const sources = [
  { id: "los-sk", name: "LOS-SK", icon: "assets/icons/los-sk.svg" },
  { id: "squad", name: "SQUAD", icon: "assets/icons/squad.svg" },
  {
    id: "shootingarea",
    name: "Shooting Area",
    icon: "assets/icons/shootingarea.svg",
  },
  { id: "sads", name: "SADS", icon: "assets/icons/sads.svg" },
];
const eventsElement = document.querySelector("#events");
const statusElement = document.querySelector("#status");
const sourceStatusElement = document.querySelector("#source-status");
const feedbackButton = document.querySelector("#feedback-button");

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

  const loadedSources = await Promise.all(
    sources.map(async (source) => {
      const manifestPath = `data/${source.id}.json`;
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

      const csvPath = `data/${manifest.file}`;
      const response = await fetch(csvPath, { cache: "no-cache" });
      if (!response.ok) {
        throw new Error(`Nepodarilo sa načítať ${csvPath} (${response.status}).`);
      }
      return { source, manifest, text: await response.text() };
    }),
  );

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
        location: row[columns.location],
        url: row[columns.url],
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

  return { events, loadedSources };
}

function renderSourceStatus(loadedSources) {
  sourceStatusElement.replaceChildren();
  const week = 7 * 24 * 60 * 60 * 1000;
  for (const { source, manifest } of loadedSources) {
    const item = document.createElement("article");
    item.setAttribute("role", "listitem");
    const heading = document.createElement("div");
    const name = document.createElement("h3");
    const state = document.createElement("p");
    const icon = document.createElement("img");
    let status;
    if (manifest.last_run_status === "failed") {
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
    heading.className = "source-card-heading";
    name.className = "source-name";
    state.className = "source-state";
    icon.className = "source-icon";
    icon.src = source.icon;
    icon.alt = "";
    icon.loading = "lazy";
    icon.addEventListener("error", () => icon.remove());
    name.textContent = source.name;
    heading.append(icon, name);
    item.append(heading, state);

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
      item.append(lastSuccess);
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
      item.append(lastFailure);
    }

    sourceStatusElement.append(item);
  }
}

function renderEvents({ events, loadedSources }) {
  renderSourceStatus(loadedSources);
  const seen = new Set();
  events = events.filter((event) => {
    const location = event.location
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, " ")
      .trim();
    const key = `${event.date}|${location}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
  events.sort((left, right) => left.date.localeCompare(right.date));
  eventsElement.replaceChildren();

  if (events.length === 0) {
    statusElement.textContent = "Momentálne nie sú naplánované žiadne nadchádzajúce súťaže.";
    return;
  }

  const rows = events.map((event) => {
    const row = document.createElement("tr");
    const sourceCell = document.createElement("td");
    const dateCell = document.createElement("td");
    const locationCell = document.createElement("td");
    const linkCell = document.createElement("td");
    const icon = document.createElement("img");
    const link = document.createElement("a");

    sourceCell.className = "source-cell";
    icon.className = "source-icon";
    icon.src = event.source.icon;
    icon.alt = event.source.name;
    icon.title = event.source.name;
    icon.loading = "lazy";
    icon.addEventListener("error", () => icon.remove());
    sourceCell.append(icon);
    dateCell.textContent = new Intl.DateTimeFormat("sk-SK", {
      dateStyle: "medium",
      timeZone: "UTC",
    }).format(new Date(`${event.date}T00:00:00Z`));
    locationCell.textContent = event.location;

    const url = new URL(event.url, window.location.href);
    if (url.protocol !== "https:" && url.protocol !== "http:") {
      throw new Error("Odkaz na súťaž musí používať HTTP alebo HTTPS.");
    }
    link.href = url.href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.className = "event-link";
    link.textContent = "Otvoriť pretek ↗";
    link.setAttribute(
      "aria-label",
      `Otvoriť detail preteku na stránke ${event.source.name}`,
    );
    link.title = `Detail na stránke ${event.source.name}`;

    linkCell.append(link);
    row.append(sourceCell, dateCell, locationCell, linkCell);
    return row;
  });

  eventsElement.append(...rows);
  statusElement.textContent = "";
}

loadEvents()
  .then(renderEvents)
  .catch((error) => {
    statusElement.textContent = "Súťaže sa nepodarilo načítať. Skúste to neskôr.";
    console.error(error);
  });
