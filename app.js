const csvFiles = ["data/los-sk.csv"];
const eventsElement = document.querySelector("#events");
const statusElement = document.querySelector("#status");

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
  const csvTexts = await Promise.all(
    csvFiles.map(async (file) => {
      const response = await fetch(file, { cache: "no-cache" });
      if (!response.ok) {
        throw new Error(`Nepodarilo sa načítať ${file} (${response.status}).`);
      }
      return response.text();
    }),
  );
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  return csvTexts.flatMap((text) => {
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
}

function renderEvents(events) {
  events.sort((left, right) => left.date.localeCompare(right.date));
  eventsElement.replaceChildren();

  if (events.length === 0) {
    statusElement.textContent = "Momentálne nie sú naplánované žiadne nadchádzajúce súťaže.";
    return;
  }

  const rows = events.map((event) => {
    const row = document.createElement("tr");
    const dateCell = document.createElement("td");
    const locationCell = document.createElement("td");
    const linkCell = document.createElement("td");
    const link = document.createElement("a");

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
    link.textContent = "Detail súťaže";

    linkCell.append(link);
    row.append(dateCell, locationCell, linkCell);
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
