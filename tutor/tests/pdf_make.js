/* Baut mit notes.js ein PDF aus JPEG-Dateien: node tests/pdf_make.js out.pdf a.jpg [b.jpg …] */
const fs = require("node:fs");
const N = require("../web/notes.js");
const [out, ...jpgs] = process.argv.slice(2);
const pages = jpgs.map((f) => ({ jpeg: new Uint8Array(fs.readFileSync(f)), width: 1240, height: 1754 }));
fs.writeFileSync(out, N.buildPdf(pages));
