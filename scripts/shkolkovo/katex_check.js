// Фаза 4: прогоняет список математических вставок через настоящий katex.renderToString.
// Использование: node katex_check.js <input.json> <output.json> <katex_install_dir>
// katex_install_dir — папка ВНЕ репозитория, где стоит `npm i katex` (там node_modules/katex).
// input.json: [{ "id": 0, "displayMode": false, "tex": "x^2" }, ...]
// output.json: [{ "id": 0, "ok": true }, { "id": 1, "ok": false, "error": "..." }, ...]

const fs = require("fs");
const path = require("path");

const [, , inputPath, outputPath, katexDir] = process.argv;
if (!inputPath || !outputPath || !katexDir) {
    console.error("Использование: node katex_check.js <input.json> <output.json> <katex_install_dir>");
    process.exit(1);
}

const katex = require(path.join(katexDir, "node_modules", "katex"));

const items = JSON.parse(fs.readFileSync(inputPath, "utf-8"));
const results = new Array(items.length);

for (let i = 0; i < items.length; i++) {
    const item = items[i];
    try {
        katex.renderToString(item.tex, {
            throwOnError: true,
            displayMode: !!item.displayMode,
            strict: "ignore",
        });
        results[i] = { id: item.id, ok: true };
    } catch (e) {
        results[i] = { id: item.id, ok: false, error: String(e && e.message ? e.message : e) };
    }
}

fs.writeFileSync(outputPath, JSON.stringify(results), "utf-8");
console.log(`done: ${items.length} items`);
