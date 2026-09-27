import { describe, expect, it } from "vitest";
import { balancedLines, blockPitch, breakLines, CAP_TO_PITCH, layoutBox, lineCounts, readOutline, layoutSound, layoutText, lineProfile, pagePitch } from "./layout";

// „monospace" font: svaki znak je širok 0,6 veličine slova, velika slova su 0,7 visine
const measure = (text: string) => text.length * 0.6;
const options = { pitch: 35, capRatio: 0.7, shape: "bubble" as const };
const baseSize = (CAP_TO_PITCH * 35) / 0.7; // 30 px

describe("slaganje teksta", () => {
  it("srednji redovi oblačića su najširi", () => {
    const profile = lineProfile(5, "bubble");

    expect(profile[2]).toBe(1);
    expect(profile[0]).toBeCloseTo(profile[4]);
    expect(profile[0]).toBeLessThan(profile[1]);
    expect(lineProfile(3, "rect")).toEqual([1, 1, 1]);
  });

  it("veličina i razmak redova odgovaraju originalu", () => {
    const layout = layoutText("TODE! JE LI SVE MIRNO?", { x: 0, y: 0, width: 400, height: 70 }, measure, options);

    expect(layout.size).toBeCloseTo(baseSize);
    expect(layout.size * layout.lineHeight).toBeCloseTo(35);
    expect(layout.fits).toBe(true);
    expect(layout.lines.join(" ").replace(/- /g, "")).toBe("TODE! JE LI SVE MIRNO?");
  });

  it("tekst je centriran u okviru", () => {
    const box = { x: 100, y: 200, width: 400, height: 105 };
    const layout = layoutText("STIGLI SMO!", box, measure, options);

    expect(layout.x + layout.width / 2).toBeCloseTo(300);
    expect(layout.y + layout.height / 2).toBeCloseTo(252.5);
  });

  it("rastavlja reč kad bi red ostao poluprazan", () => {
    // širina reda: 14 znakova pri 30 px; „BESTRAGA! PRAVA" ima 15
    const lines = breakLines(["BESTRAGA!", "PRAVA", "JE", "SREĆA"], [14 * 18, 14 * 18, 14 * 18], 30, measure);

    expect(lines).toEqual(["BESTRAGA! PRA-", "VA JE SREĆA"]);
  });

  it("predugačak tekst prvo širi okvir, pa tek onda smanjuje slova", () => {
    const text = "SLUČAJNO SAM SREO LITL DŽOA S TVOJOM PORUKOM I ODMAH KRENUO";
    const roomy = layoutText(text, { x: 0, y: 0, width: 300, height: 175 }, measure, options);
    const tight = layoutText(text, { x: 0, y: 0, width: 120, height: 35 }, measure, options);

    expect(roomy.size).toBeCloseTo(baseSize);
    expect(tight.size).toBeLessThan(baseSize);
    expect(tight.fits).toBe(false);
  });

  it("onomatopeja popunjava okvir jednim redom", () => {
    const layout = layoutSound("SCVAK", { x: 10, y: 20, width: 300, height: 100 }, measure, 0.7);

    expect(layout.lines).toEqual(["SCVAK"]);
    expect(measure("SCVAK") * layout.size).toBeLessThanOrEqual(300);
  });

  it("razmak redova stranice je medijana blokova sa više redova", () => {
    const blocks = [
      { height: 140, text: "A\nB\nC\nD", kind: "speech" },
      { height: 70, text: "A\nB", kind: "speech" },
      { height: 36, text: "AH!", kind: "speech" }, // jedan red: ne računa se
      { height: 300, text: "SWACK", kind: "sfx" },
    ];

    expect(pagePitch(blocks, 2200)).toBe(35);
    expect(pagePitch([], 2240)).toBe(35);
  });

  it("prvo dodaje red, pa tek onda širi okvir", () => {
    // jedan red originala (35 px), prevod ne staje u širinu: ide u dva reda iste širine
    const layout = layoutText("TO JE ON, BAŠ ON!", { x: 0, y: 0, width: 200, height: 35 }, measure, options);

    expect(layout.lines.length).toBe(2);
    expect(layout.width).toBeLessThanOrEqual(200); // nije širio okvir
    expect(layout.size).toBeCloseTo(baseSize);
  });

  it("sa izmerenim oblikom red se skraćuje i pomera gde je oblačić zasečen", () => {
    // oblačić 100..500 po širini, ali od y=160 naniže desna strana je zasečena na 380
    const ys = Array.from({ length: 41 }, (_, i) => 50 + i * 5);
    const outline = [...ys.map((y) => [100, y]), ...[...ys].reverse().map((y) => [y >= 160 ? 380 : 500, y])];
    const box = { x: 150, y: 80, width: 300, height: 140 };
    const text = "SLUČAJNO SAM NALETEO NA LITL DŽOA SA TVOJOM PORUKOM!";

    const layout = layoutText(text, box, measure, { ...options, outline });

    const pad = 0.3 * 35;
    layout.placements.forEach((placement, i) => {
      const lineWidth = measure(layout.lines[i]) * layout.size;
      const middle = placement.y + (layout.size * layout.lineHeight) / 2;
      const cap = (CAP_TO_PITCH * 35 * layout.size) / baseSize; // slova su možda smanjena
      const right = middle + cap / 2 + 3.5 >= 160 ? 380 : 500;
      expect(placement.x + placement.width / 2 + lineWidth / 2).toBeLessThanOrEqual(right - pad + 0.01);
    });
    expect(layout.fits).toBe(true);
  });

  it("ravnomerno raspoređuje reči po redovima", () => {
    // pohlepno: „BESTRAGA PRAVA JE" / „SREĆA"; ravnomerno: „BESTRAGA PRAVA" / „JE SREĆA"
    const words = "BESTRAGA PRAVA JE SREĆA".split(" ");
    const widths = [20 * 18, 20 * 18];

    const greedy = breakLines(words, widths, 30, measure) ?? [];
    const balanced = balancedLines(words, widths, 30, measure) ?? [];

    const spread = (lines: string[]) => Math.max(...lines.map((l) => l.length)) - Math.min(...lines.map((l) => l.length));
    expect(balanced).toHaveLength(2);
    expect(spread(balanced)).toBeLessThan(spread(greedy));
  });

  it("prvo proba broj redova originala, pa susedne", () => {
    expect(lineCounts(3, 6)).toEqual([3, 2, 4, 1, 5, 6]);
    expect(lineCounts(1, 3)).toEqual([1, 2, 3]);
    expect(lineCounts(5, 3)).toEqual([3, 2, 1]);
  });

  it("ne rastavlja reč kad tekst staje i bez toga", () => {
    const words = "MORAMO OBAVESTITI RAMONA I ŠERIFE!".split(" ");

    const lines = balancedLines(words, [18 * 18, 18 * 18, 18 * 18], 30, measure) ?? [];

    expect(lines.join(" ")).not.toContain("-");
  });

  it("poštuje ručne prelome redova", () => {
    const layout = layoutText("TO JE\nON!", { x: 0, y: 0, width: 400, height: 35 }, measure, options);

    expect(layout.lines).toEqual(["TO JE", "ON!"]);
    expect(layout.fits).toBe(true);
  });

  it("ručna veličina se ne smanjuje sama, a prored se množi", () => {
    const box = { x: 0, y: 0, width: 200, height: 70 };
    const bigger = layoutText("TODE! JE LI SVE MIRNO?", box, measure, { ...options, scale: 1.3 });
    const spaced = layoutText("TODE! JE LI SVE MIRNO?", box, measure, { ...options, lineSpacing: 1.2 });

    expect(bigger.size).toBeCloseTo(baseSize * 1.3);
    expect(spaced.lineHeight).toBeCloseTo((35 / baseSize) * 1.2); // veličinu slova i dalje bira automatika
  });

  it("pravougaonik detektora nije oblik oblačića: slaže se u elipsu okvira", () => {
    // posle ponovne obrade stranice detektor upiše 4 ugla oblačića u isto polje
    const rect = [[530, 1628], [890, 1628], [890, 1820], [530, 1820]];
    const box = { x: 543, y: 1641, width: 330, height: 172 };

    const layout = layoutText("DA LI JE ŠERIF TOG MESTA I DALJE STARI BIL PARSON?", box, measure, { ...options, outline: rect });

    expect(readOutline(rect)).toBeNull();
    expect(layout.fits).toBe(true);
  });

  it("ručna veličina prihvata i manje redova od predviđenih", () => {
    // okvir originala ima 3 reda, a skraćen prevod staje u 2
    const layout = layoutText("STIGLI SMO! VOREN TAUN JE TU!", { x: 0, y: 0, width: 420, height: 105 }, measure, { ...options, scale: 0.8 });

    expect(layout.fits).toBe(true);
    expect(layout.size).toBeCloseTo(baseSize * 0.8);
  });
});

describe("promašeno merenje oblačića (Ramon 12, str. 47 i 96)", () => {
  // oblak od kojeg je izmerena samo tanka traka belog (33 px u bloku visokom 467)
  const box = { x: 0, y: 0, width: 400, height: 400 };
  const sliver = Array.from({ length: 11 }, (_, i) => 190 + i * 3);
  const tiny = [...sliver.map((y) => [40, y]), ...[...sliver].reverse().map((y) => [360, y])];
  const text = "ZAŠTO? MISLIŠ LI STVARNO DA BI IH NEKO MOGAO PRATITI ČAK DOVDE?";

  it("oblik manji od pola bloka se ne koristi, važi elipsa u okviru", () => {
    const layout = layoutText(text, box, measure, { ...options, outline: tiny });

    expect(layout.fits).toBe(true);
    // svi redovi ostaju u okviru bloka, a ne u širini trake koja je slučajno izmerena
    for (const placement of layout.placements) {
      expect(placement.x).toBeGreaterThanOrEqual(box.x);
      expect(placement.x + placement.width).toBeLessThanOrEqual(box.x + box.width);
    }
  });

  it("oblik do pola oblačića (obod šešira preseče merenje, 12/47 blok 8) se ne koristi", () => {
    // blok 460 × 466, a izmereno je samo gornjih 252 px (0,54): 14 redova originala ne sme u tu polovinu
    const block = { x: 0, y: 0, width: 460, height: 466 };
    const rows = Array.from({ length: 64 }, (_, i) => i * 4);
    const top = [...rows.map((y) => [0, y]), ...[...rows].reverse().map((y) => [440, y])];
    const long = `${text} ČAK I AKO PRETPOSTAVIMO DA NISU ISPRIČALI GOMILU LAŽI, APSOLUTNO JE NEZAMISLIVO.`;

    const layout = layoutText(long, block, measure, { ...options, outline: top });

    const bottom = layout.placements[layout.placements.length - 1].y + layout.size * layout.lineHeight;
    expect(bottom).toBeGreaterThan(252); // tekst koristi ceo oblačić, a ne samo izmereni deo
  });

  it("uzak oblik (samo jedna reč belog) se takođe odbacuje", () => {
    const rows = Array.from({ length: 21 }, (_, i) => 100 + i * 10);
    const narrow = [...rows.map((y) => [190, y]), ...[...rows].reverse().map((y) => [210, y])];

    const layout = layoutText("KRATKO", box, measure, { ...options, outline: narrow });

    expect(layout.fits).toBe(true);
  });
});

describe("oblačić pomeren u odnosu na okvir (Ramon 12, str. 74 i 86)", () => {
  // detektor je zahvatio okvir više nego što je beli prostor: oblak je 140 px niže
  const box = { x: 0, y: 0, width: 400, height: 300 };
  const rows = Array.from({ length: 61 }, (_, i) => 140 + i * 5);
  const outline = [...rows.map((y) => [20, y]), ...[...rows].reverse().map((y) => [380, y])];

  it("tekst se uvlači u izmereni oblačić, umesto da ispadne iz njega", () => {
    const layout = layoutText("NEZAMISLIVO JE DA BI IH NEKO PRATIO SVE DO OVDE!", box, measure, { ...options, outline });

    expect(layout.fits).toBe(true);
    expect(layout.y).toBeGreaterThanOrEqual(rows[0]);
    expect(layout.y + layout.height).toBeLessThanOrEqual(rows[rows.length - 1]);
  });

  it("kad oblačić staje u okvir, tekst ostaje na sredini bloka", () => {
    const inside = Array.from({ length: 51 }, (_, i) => 20 + i * 5); // 20..270, veći od teksta
    const shape = [...inside.map((y) => [20, y]), ...[...inside].reverse().map((y) => [380, y])];

    const layout = layoutText("STIGLI SMO!", box, measure, { ...options, outline: shape });

    expect(layout.y + layout.height / 2).toBeCloseTo(box.y + box.height / 2);
  });
});

describe("ručni prelom usred teksta (12/47 blok 8)", () => {
  const box = { x: 0, y: 0, width: 460, height: 466 };
  const text =
    "ZAŠTO? ZAR ZAISTA\nMISLIŠ DA BI NEKO MOGAO DA SE POJAVI, NA TRAGU TOM STARCU I NJEGOVOJ ĆERKI?... ČAK I AKO " +
    "PRETPOSTAVIMO DA NISU ISPRIČALI GOMILU LAŽI, APSOLUTNO JE NEZAMISLIVO DA BI IH NEKO MOGAO PRATITI SVE DO OVDE IZ NJUJORKA!";

  it("prelom je obavezan, a ostatak teksta se prelama sam", () => {
    const layout = layoutText(text, box, measure, { pitch: 33, capRatio: 0.7, shape: "bubble" });

    expect(layout.fits).toBe(true);
    expect(layout.lines[0]).toBe("ZAŠTO? ZAR ZAISTA");
    expect(layout.lines.length).toBeGreaterThan(4);
    expect(layout.lines.join(" ").replace(/- /g, "").replace(/-(?=[A-ZČĆŽŠĐ])/g, "")).toContain("NJUJORKA!");
  });

  it("ručno raspoređeni redovi se ne prelamaju ni kad neki ne staje: ostaje crven, panel kaže koji je", () => {
    const lines = [
      "ZAŠTO? ZAR ZAISTA", "MISLIŠ DA BI NEKO MOGAO", "DA SE POJAVI, NA TRAGU", "TOM STARCU I NJEGOVOJ",
      "ĆERKI?... ČAK I AKO", "PRETPOSTAVIMO DA", "NISU ISPRIČALI", "GOMILU LAŽI,", "APSOLUTNO JE NEZAMISLIVO",
      "DA BI IH NEKO MOGAO", "PRATITI SVE DO OVDE", "IZ NJUJORKA!",
    ];
    const layout = layoutText(lines.join("\n"), box, measure, { pitch: 33, capRatio: 0.7, shape: "bubble" });
    expect(layout.lines).toEqual(lines);
    if (!layout.fits) expect(layout.overflow?.line).toBeGreaterThan(0);
  });

  it("kad svaki red ima svoj prelom, raspored ostaje tačno kako je upisan", () => {
    const layout = layoutText("ZAŠTO?\nZAR ZAISTA MISLIŠ?", box, measure, { pitch: 33, capRatio: 0.7, shape: "bubble" });
    expect(layout.lines).toEqual(["ZAŠTO?", "ZAR ZAISTA MISLIŠ?"]);
  });
});

describe("stepenasta naracija (str. 13 Ramona 12)", () => {
  // traka naracije je puna širina do y=183, a ispod nje ostaje samo levi deo (desno je crtež)
  const box = { x: 84, y: 98, width: 1615, height: 121 };
  const rows = Array.from({ length: 39 }, (_, i) => 101 + i * 3);
  const outline = [
    ...rows.map((y) => [100, y]),
    ...[...rows].reverse().map((y) => [y <= 183 ? 1700 : 630, y]),
  ];
  const original = "FU RITROVATO DA UN CARRO DI COLONI,\nDALLA COSTA, MA COME FOSSE\nNI E' UN VERO MISTERO!";
  const translation =
    "PRONAŠLA SU GA KOLONISTIČKA KOLA, NEKOLIKO DANA KASNIJE,\n" +
    "MNOGO MILJA DALEKO OD OBALE, ALI KAKO JE U TAKVOM STANJU USPEO DA STIGNE DO TAMO,\n" +
    "PRAVA JE MISTERIJA!";

  it("blok sa bar dva reda koristi svoj razmak redova, a ne stranicin", () => {
    expect(blockPitch(121, original, 50)).toBeCloseTo(40.3, 1); // naracija je sitnija od govora
    expect(blockPitch(121, "JEDAN RED", 50)).toBe(50); // jedan red: razmak se ne može izmeriti
    expect(blockPitch(40, original, 50)).toBe(35); // 13,3 je predaleko od stranicinog razmaka
  });

  it("ručni prelomi staju: donji red ide u uži deo trake, slova se smanje koliko treba", () => {
    const pitch = blockPitch(box.height, original, 50);

    const layout = layoutText(translation, box, measure, { pitch, capRatio: 0.7, shape: "bubble", outline });

    expect(layout.lines).toHaveLength(3);
    expect(layout.fits).toBe(true);
    expect(layout.size).toBeLessThan((CAP_TO_PITCH * pitch) / 0.7); // smanjena, jer srednji red je dugačak
    expect(layout.placements[2].width).toBeLessThan(layout.placements[1].width / 2);
  });

  it("kaže koji red je preširok i koliko, da korisnik zna šta da promeni", () => {
    const pitch = blockPitch(box.height, original, 50);

    // zadata veličina se ne menja sama: srednji red ostaje preširok
    const layout = layoutText(translation, box, measure, { pitch, capRatio: 0.7, shape: "bubble", outline, scale: 0.95 });

    expect(layout.fits).toBe(false);
    expect(layout.overflow?.line).toBe(2);
    expect(layout.overflow?.extra).toBeGreaterThan(0);
  });

  it("oblik izmeren samo do stepenika (68 % bloka) se ne koristi, važi okvir bloka", () => {
    // zato se oblik meri iz reda u red: nedovršeno merenje je ispod granice od 0,7 i odbacuje se
    const short = rows.filter((y) => y <= 183);
    const cut = [...short.map((y) => [100, y]), ...[...short].reverse().map((y) => [1700, y])];
    const pitch = blockPitch(box.height, original, 50);

    const partial = layoutText(translation, box, measure, { pitch, capRatio: 0.7, shape: "bubble", outline: cut });
    const plain = layoutText(translation, box, measure, { pitch, capRatio: 0.7, shape: "bubble" });

    expect(partial.placements).toEqual(plain.placements);
  });
});

describe("razmak redova stranice", () => {
  const block = (height: number, text: string, kind = "speech") => ({ height, text, kind });

  it("medijana blokova sa bar dva reda", () => {
    const blocks = [block(70, "PRVI\nRED"), block(105, "A\nB\nC"), block(40, "JEDAN RED")];

    expect(pagePitch(blocks, 2457)).toBe(35);
  });

  it("netipičan blok ne izvitoperi celu stranu", () => {
    // velika traka sa dva reda daje medijanu 148 px, a strana ima ~38 px po redu
    const blocks = [block(297, "NE-\nZAUSTAVLJIVI", "caption")];

    const pitch = pagePitch(blocks, 2457);

    expect(pitch).toBeLessThan(60);
    expect(pitch).toBeGreaterThan(30);
  });

  it("bez blokova sa dva reda uzima se visina strane", () => {
    expect(pagePitch([block(40, "SAMO JEDAN RED")], 2457)).toBeCloseTo(2457 / 64);
  });
});

describe("levo poravnanje u oblačiću", () => {
  // oblačić: gornji i donji redovi su uži (zaobljenje), srednji je pun
  const rows = Array.from({ length: 13 }, (_, i) => 100 + i * 10);
  const inset = (y: number) => (y < 130 || y > 190 ? 60 : 0);
  const outline = [
    ...rows.map((y) => [100 + inset(y), y]),
    ...[...rows].reverse().map((y) => [700 - inset(y), y]),
  ];
  const box = { x: 100, y: 100, width: 600, height: 120 };
  const options = { pitch: 40, capRatio: 0.7, shape: "bubble" as const, outline };
  const text = "PRVI RED OVDE\nDRUGI RED JE MALO DUŽI\nTREĆI RED";
  const lefts = (result: ReturnType<typeof layoutText>) => result.placements.map((item) => Math.round(item.x));

  it("bez poravnanja svaki red sedi u svom, različito širokom mestu", () => {
    expect(new Set(lefts(layoutText(text, box, measure, options))).size).toBeGreaterThan(1);
  });

  it("sa poravnanjem levo svi redovi počinju na istoj ivici, unutar oblačića", () => {
    const ragged = layoutText(text, box, measure, options);
    const aligned = layoutText(text, box, measure, { ...options, align: "left" });

    expect(new Set(lefts(aligned)).size).toBe(1);
    expect(lefts(aligned)[0]).toBe(Math.max(...lefts(ragged))); // najuži red određuje ivicu
    expect(aligned.lines).toEqual(ragged.lines);
  });

  it("kad tekst ne staje ni najmanjim slovima, poruka meri prema oblačiću, a ne prema crtanju", () => {
    // mali okvir i dugačak tekst: crta se šire od okvira, ali poruka kaže koliko fali
    const tight = { x: 100, y: 100, width: 120, height: 40 };
    const text = "OVO JE MNOGO DUŽI TEKST NEGO ŠTO U OVAJ OBLAČIĆ MOŽE DA STANE";
    const layout = layoutText(text, tight, measure, { pitch: 40, capRatio: 0.7, shape: "bubble" });

    expect(layout.fits).toBe(false);
    expect(layout.overflow).not.toBeNull();
    expect(layout.overflow!.extra).toBeGreaterThan(0);
  });

  it("red koji tako ne bi stao ostaje u svom mestu, da ne izađe iz oblačića", () => {
    const wide = "PRVI RED OVDE\nDRUGI RED JE OVDE ZNATNO DUŽI OD SVIH OSTALIH\nTREĆI RED";

    const aligned = layoutText(wide, box, measure, { ...options, align: "left" });

    expect(aligned.placements[0].x).toBeGreaterThan(aligned.placements[1].x);
  });

  it("sa poravnanjem desno svi redovi se završavaju na istoj ivici", () => {
    const aligned = layoutText(text, box, measure, { ...options, align: "right" });

    const rights = aligned.placements.map((item) => Math.round(item.x + item.width));
    expect(new Set(rights).size).toBe(1);
  });
});

describe("uklopi u okvir (uredničke strane)", () => {
  const box = { x: 100, y: 200, width: 500, height: 1600 };
  const words = "DRAGI RAMONOVI FANOVI ALBUM KOJI DRŽITE U RUKAMA PREDSTAVLJA DVOSTRUKI BIS".split(" ");
  const long = Array.from({ length: 12 }, () => words.join(" ")).join(" "); // ~900 znakova, kao na str. 4

  it("bira najveća slova sa kojima ceo tekst staje u okvir", () => {
    const layout = layoutBox(long, box, measure, {});

    expect(layout.fits).toBe(true);
    expect(layout.lines.length * layout.size * layout.lineHeight).toBeLessThanOrEqual(box.height);
    expect(layout.lines.every((line) => measure(line) * layout.size <= box.width)).toBe(true);
    // malo veća slova više ne bi stala
    const bigger = layout.size * 1.08;
    const rows = Math.ceil(measure(long) * bigger / (box.width * 0.9));
    expect(rows * bigger * layout.lineHeight).toBeGreaterThan(box.height * 0.9);
  });

  it("slova nisu vezana za razmak redova originala: mali okvir dobija sitna slova", () => {
    const small = layoutBox(long, { ...box, height: 400 }, measure, {});

    expect(small.fits).toBe(true);
    expect(small.size).toBeLessThan(layoutBox(long, box, measure, {}).size);
  });

  it("prazan red deli pasuse, a redovi pasusa se ne preklapaju", () => {
    const layout = layoutBox("PRVI PASUS.\n\nDRUGI PASUS.", box, measure, {});

    expect(layout.lines).toContain("");
    const ys = layout.placements.map((item) => item.y);
    expect(ys).toEqual([...ys].sort((a, b) => a - b));
  });

  it("ručno uvećan tekst koji više ne staje je označen", () => {
    const layout = layoutBox(long, box, measure, { scale: 1.5 });

    expect(layout.fits).toBe(false);
  });
});

describe("naglasak u slaganju", () => {
  it("naglašena reč se rastavlja kao i obična, a zvezdice ostaju na krajevima", async () => {
    const { emphasisMeasure } = await import("./emphasis");
    const measure = emphasisMeasure((text: string) => text.length * 0.6);
    const lines = breakLines(["NE...", "OSEĆAM", "SE", "*BESKORISNO*."], [60, 60, 60, 60], 10, measure);
    expect(lines?.slice(-2)).toEqual(["*BESKORI-", "SNO*."]);
  });
});
