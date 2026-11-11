// Optional template authoring step. Requires the Codex bundled @oai/artifact-tool.
// Main case generation copies these checked-in templates without editing them.
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const out = path.join(root, 'cases', 'templates');
const qa = path.join(root, '.runtime', 'edge-qa', 'xlsx');
await fs.mkdir(out, { recursive: true });
await fs.mkdir(qa, { recursive: true });
const contract = '26/01/01-77';

function payroll(wb, name, main = 100000, extra = 10000, project = contract, number = 'ВЕД-EC-2026-01') {
  const ws = wb.worksheets.add(name);
  ws.mergeCells('A1:D1');
  ws.getRange('A1').values = [['РАСЧЕТНАЯ ВЕДОМОСТЬ ПО ОПЛАТЕ ТРУДА']];
  ws.mergeCells('A2:D2');
  ws.getRange('A2').values = [[`Документ: ${number}`]];
  ws.mergeCells('A3:D3');
  ws.getRange('A3').values = [[`Проект: ${project} | Период: Январь 2026`]];
  ws.getRange('A5:D8').values = [
    ['Код статьи', 'Вид начисления', 'Сумма, руб.', 'Основание'],
    ['0201', 'Основная заработная плата', main, 'Расчёт начислений'],
    ['0202', 'Дополнительная заработная плата', extra, 'Доплаты за месяц'],
    [null, 'ИТОГО', null, null],
  ];
  ws.getRange('C8').formulas = [['=SUM(C6:C7)']];
  ws.getRange('A6:A7').setNumberFormat('0000');
  ws.getRange('C6:C8').setNumberFormat('#,##0.00');
  return ws;
}

function insurance(wb, amount) {
  const ws = wb.worksheets.add('Расчет взносов');
  for (const [row, text] of [[1, 'РАСЧЕТ СТРАХОВЫХ ВЗНОСОВ'], [2, 'Документ: ВЗН-EC-2026-01'], [3, `Проект: ${contract} | Период: Январь 2026`]]) {
    ws.mergeCells(`A${row}:D${row}`);
    ws.getRange(`A${row}`).values = [[text]];
  }
  ws.getRange('A5:D6').values = [
    ['База начислений, руб.', 'Начислено взносов, руб.', 'Код статьи', 'Комментарий'],
    [amount === 0 ? 0 : amount === 33000.01 ? 110000.03 : 110000, amount, '0300', 'Сводное начисление за январь'],
  ];
  ws.getRange('A6:B6').setNumberFormat('#,##0.00');
  ws.getRange('C6').setNumberFormat('0000');
  return ws;
}

const definitions = [
  ['payroll', wb => payroll(wb, 'Ведомость')],
  ['insurance', wb => insurance(wb, 33000)],
  ['payroll_pennies', wb => payroll(wb, 'Ведомость', 100000.01, 10000.02)],
  ['insurance_pennies', wb => insurance(wb, 33000.01)],
  ['payroll_zero', wb => payroll(wb, 'Ведомость', 0, 0)],
  ['insurance_zero', wb => insurance(wb, 0)],
  // Deliberately text-typed amounts: this is a negative parser fixture.
  ['payroll_text', wb => payroll(wb, 'Ведомость', '100000,00', '10000,00')],
  ['payroll_second', wb => payroll(wb, 'Ведомость', 100000, 10000, contract, 'ВЕД-EC-2026-01-B')],
  ['payroll_mixed_sheets', wb => {
    payroll(wb, 'Проверяемый договор');
    payroll(wb, 'Другой договор', 999999, 1, '26/02/02-99', 'ВЕД-OTHER-01');
  }],
];

for (const [name, build] of definitions) {
  const wb = Workbook.create();
  build(wb);
  for (let i = 0; i < wb.worksheets.items.length; i++) {
    const ws = wb.worksheets.getItemAt(i);
    ws.showGridLines = false;
    ws.getRange('A1:D9').format.font = { name: 'Arial', size: 11, color: '#172B40' };
    ws.getRange('A1:D1').format.font = { name: 'Arial', size: 14, bold: true, color: '#000000' };
    ws.getRange('A1:D9').format.rowHeight = 27;
    ws.getRange('A1:A9').format.columnWidth = 23;
    ws.getRange('B1:B9').format.columnWidth = 49;
    ws.getRange('C1:C9').format.columnWidth = 23;
    ws.getRange('D1:D9').format.columnWidth = 38;
    ws.getRange('A5:D5').format = { fill: '#EAF0F7', font: { name: 'Arial', size: 11, bold: true, color: '#172B40' }, rowHeight: 42, wrapText: true };
    ws.getRange('A5:D8').format.borders = { preset: 'all', style: 'thin', color: '#D9D9D9' };
    ws.getRange('A1:D9').format.verticalAlignment = 'center';
  }
  wb.recalculate();
  const sheetNames = (await wb.inspect({ kind: 'sheet', include: 'name', maxChars: 1500 })).ndjson;
  for (let i = 0; i < wb.worksheets.items.length; i++) {
    const ws = wb.worksheets.getItemAt(i);
    const render = await wb.render({ sheetName: ws.name, range: 'A1:D9', scale: 1.5, format: 'png' });
    await fs.writeFile(path.join(qa, `${name}-${i}.png`), new Uint8Array(await render.arrayBuffer()));
  }
  const output = await SpreadsheetFile.exportXlsx(wb);
  await output.save(path.join(out, name + '.xlsx'));
  console.log(name, sheetNames.replaceAll('\n', ' '));
}
