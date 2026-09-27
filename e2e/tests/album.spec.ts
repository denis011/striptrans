// E2E: uvoz malog stripa → blokovi i prevod (preko API-ja, bez AI troška) → čišćenje → izvoz CBZ i PDF.
// Pokretanje: make test-e2e (compose profil „e2e", radi protiv pokrenute aplikacije).

import { type APIRequestContext, type Page, expect, test } from "@playwright/test";
import AdmZip from "adm-zip";
import jpeg from "jpeg-js";
import { PNG } from "pngjs";

const WIDTH = 900;
const HEIGHT = 1200;
const BUBBLE = { x: 170, y: 220, width: 560, height: 160 }; // okvir teksta u oblačiću
const INTERIOR = { x: 260, y: 250, width: 380, height: 100 }; // unutrašnjost oblačića za merenje

/** Strana nacrtana u browseru: oblačić sa italijanskim tekstom, ili siva „reklama". */
async function drawPage(page: Page, lines: string[] | null): Promise<Buffer> {
  const dataUrl = await page.evaluate(
    ({ width, height, lines }) => {
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d") as CanvasRenderingContext2D;
      ctx.fillStyle = lines ? "#fff" : "#aaa";
      ctx.fillRect(0, 0, width, height);
      if (lines) {
        ctx.strokeStyle = "#000";
        ctx.lineWidth = 5;
        ctx.strokeRect(40, 40, width - 80, height - 80);
        ctx.beginPath();
        ctx.ellipse(450, 300, 320, 140, 0, 0, Math.PI * 2);
        ctx.fillStyle = "#fff";
        ctx.fill();
        ctx.stroke();
        ctx.fillStyle = "#000";
        ctx.font = "bold 42px sans-serif";
        ctx.textAlign = "center";
        lines.forEach((line, i) => ctx.fillText(line, 450, 285 + i * 52));
      }
      return canvas.toDataURL("image/png");
    },
    { width: WIDTH, height: HEIGHT, lines },
  );
  return Buffer.from(dataUrl.split(",")[1], "base64");
}

async function waitForJob(request: APIRequestContext, id: number) {
  for (let i = 0; i < 240; i += 1) {
    const job = await (await request.get(`/api/jobs/${id}`)).json();
    if (!["queued", "running"].includes(job.status)) return job;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`posao ${id} nije završen`);
}

/** Udeo tamnih piksela u pravougaoniku sive slike (vrednosti 0–255, red po red). */
function darkShare(gray: (x: number, y: number) => number, area: typeof INTERIOR): number {
  let dark = 0;
  for (let y = area.y; y < area.y + area.height; y += 1) {
    for (let x = area.x; x < area.x + area.width; x += 1) if (gray(x, y) < 100) dark += 1;
  }
  return dark / (area.width * area.height);
}

test("uvoz → prevod → čišćenje → izvoz CBZ i PDF", async ({ page, request }) => {
  await page.goto("/");
  const project = await (
    await request.post("/api/projects", { data: { series_id: 1, issue_number: "E2E", translated_title: "Proba" } })
  ).json();
  try {
    // uvoz: tri strane u CBZ-u (druga je „reklama")
    const archive = new AdmZip();
    archive.addFile("001.png", await drawPage(page, ["CIAO A TUTTI,", "COME STATE?"]));
    archive.addFile("002.png", await drawPage(page, null));
    archive.addFile("003.png", await drawPage(page, ["CHE SUCCEDE", "QUI?"]));
    const imported = await request.post(`/api/projects/${project.id}/imports`, {
      multipart: { kind: "original", files: { name: "proba.cbz", mimeType: "application/zip", buffer: archive.toBuffer() } },
    });
    expect((await waitForJob(request, (await imported.json()).id)).status).toBe("done");
    const pages = await (await request.get(`/api/projects/${project.id}/pages`)).json();
    expect(pages.map((item: { width: number }) => item.width)).toEqual([WIDTH, WIDTH, WIDTH]);

    // blokovi i prevod kao da ih je uneo korisnik; reklama se preskače
    for (const [index, translation] of [
      [0, "ZDRAVO SVIMA, KAKO STE?"],
      [2, "ŠTA SE OVDE DEŠAVA?"],
    ] as const) {
      const block = await (await request.post(`/api/pages/${pages[index].id}/blocks`, { data: { ...BUBBLE, text: "X", kind: "speech" } })).json();
      await request.patch(`/api/blocks/${block.id}`, { data: { translation } });
    }
    await request.patch(`/api/pages/${pages[1].id}`, { data: { skip: true } });

    // čišćenje: italijanski tekst nestaje iz oblačića
    const clean = await (await request.post(`/api/projects/${project.id}/clean`)).json();
    expect((await waitForJob(request, clean.id)).status).toBe("done");
    const cleaned = PNG.sync.read(await (await request.get(`/api/pages/${pages[0].id}/clean-image`)).body());
    const channels = cleaned.data.length / (cleaned.width * cleaned.height);
    expect(darkShare((x, y) => cleaned.data[(y * cleaned.width + x) * channels], INTERIOR)).toBeLessThan(0.01);

    // izvoz CBZ kroz ekran „Izvoz"
    await page.goto(`/projects/${project.id}/export`);
    await page.getByRole("button", { name: "Izvezi album" }).click();
    await expect(page.getByText("Gotovo.")).toBeVisible({ timeout: 120_000 });
    const [cbzDownload] = await Promise.all([page.waitForEvent("download"), page.getByRole("link", { name: "Preuzmi" }).first().click()]);
    const cbz = new AdmZip(await cbzDownload.path());
    expect(cbz.getEntries().map((entry) => entry.entryName)).toEqual(["001.jpg", "002.jpg", "003.jpg", "ComicInfo.xml"]);
    expect(cbz.readAsText("ComicInfo.xml")).toContain("<PageCount>3</PageCount>");
    const first = jpeg.decode(cbz.readFile("001.jpg") as Buffer, { useTArray: true });
    expect([first.width, first.height]).toEqual([WIDTH, HEIGHT]);
    const firstDark = darkShare((x, y) => first.data[(y * first.width + x) * 4], INTERIOR);
    expect(firstDark).toBeGreaterThan(0.02); // složen srpski prevod je u oblačiću
    const ad = jpeg.decode(cbz.readFile("002.jpg") as Buffer, { useTArray: true });
    expect(Math.abs(ad.data[0] - 0xaa)).toBeLessThan(8); // preskočena strana je neizmenjena

    // izvoz PDF-a
    await page.getByLabel("Format albuma").selectOption("pdf");
    await page.getByRole("button", { name: "Izvezi album" }).click();
    await expect(page.getByRole("link", { name: "Preuzmi" })).toHaveCount(2, { timeout: 120_000 });
    const [pdfDownload] = await Promise.all([page.waitForEvent("download"), page.getByRole("link", { name: "Preuzmi" }).first().click()]);
    expect(pdfDownload.suggestedFilename()).toBe(`${project.series.name} E2E - Proba.pdf`); // serijal 1: ime zavisi od baze
    const pdf = (await import("node:fs")).readFileSync(await pdfDownload.path()).toString("latin1");
    expect(pdf.startsWith("%PDF")).toBe(true);
    expect(pdf.match(/\/Type\s*\/Page\b(?!s)/g)?.length).toBe(3);
  } finally {
    await request.delete(`/api/projects/${project.id}`);
  }
});
