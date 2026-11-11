# Результаты проверки сгенерированных комплектов

Проверка выполнена через multipart API, постановку задания в очередь и worker, с реальным чтением файлов и OCR. Эталонные JSON не передаются приложению.

Новые комплекты: **25 PASS, 5 KNOWN_LIMITATION, 0 FAIL, 0 UNEXPECTED_PASS**. Полный pytest: **62 passed, 5 xfailed**.

## Все сценарии

| Кейс | Результат |
|---|---|
| [00_clean](generated/00_clean/README.md) | PASS |
| [01_overstatement](generated/01_overstatement/README.md) | PASS |
| [02_understatement](generated/02_understatement/README.md) | PASS |
| [03_pennies](generated/03_pennies/README.md) | PASS |
| [04_byte_duplicate](generated/04_byte_duplicate/README.md) | PASS |
| [05_semantic_duplicate](generated/05_semantic_duplicate/README.md) | PASS |
| [06_conflicting_revision](generated/06_conflicting_revision/README.md) | PASS |
| [07_same_number_other_vendor](generated/07_same_number_other_vendor/README.md) | PASS |
| [08_wrong_contract](generated/08_wrong_contract/README.md) | PASS |
| [09_period_boundaries](generated/09_period_boundaries/README.md) | PASS |
| [10_missing_payroll](generated/10_missing_payroll/README.md) | PASS |
| [11_missing_contract](generated/11_missing_contract/README.md) | PASS |
| [12_missing_amount](generated/12_missing_amount/README.md) | PASS |
| [13_ambiguous_article](generated/13_ambiguous_article/README.md) | PASS |
| [14_corrupt_pdf](generated/14_corrupt_pdf/README.md) | PASS |
| [15_report_arithmetic](generated/15_report_arithmetic/README.md) | PASS |
| [16_report_contract](generated/16_report_contract/README.md) | PASS |
| [17_real_zeros](generated/17_real_zeros/README.md) | PASS |
| [18_credit_adjustment](generated/18_credit_adjustment/README.md) | PASS |
| [19_incomplete_package](generated/19_incomplete_package/README.md) | PASS |
| [20_vat_components](generated/20_vat_components/README.md) | KNOWN_LIMITATION |
| [21_text_typed_money](generated/21_text_typed_money/README.md) | KNOWN_LIMITATION |
| [22_overlapping_service_period](generated/22_overlapping_service_period/README.md) | KNOWN_LIMITATION |
| [23_other_contract_sheet](generated/23_other_contract_sheet/README.md) | KNOWN_LIMITATION |
| [24_formula_error](generated/24_formula_error/README.md) | KNOWN_LIMITATION |
| [25_stale_formula_cache](generated/25_stale_formula_cache/README.md) | PASS |
| [26_png_scan](generated/26_png_scan/README.md) | PASS |
| [27_wrong_report_row](generated/27_wrong_report_row/README.md) | PASS |
| [28_corrupt_xlsx_upload](generated/28_corrupt_xlsx_upload/README.md) | PASS |
| [29_duplicate_month](generated/29_duplicate_month/README.md) | PASS |

## Воспроизведённые ограничения

### 20_vat_components

Парсер пока не различает роль денежных полей в многострочном счёте.

Отличия от эталона:

- `0200.expected: expected '110000.00', got None`
- `0200.delta: expected '0.00', got None`
- `0200.status: expected 'MATCH', got 'INSUFFICIENT_DATA'`
- `0300.expected: expected '33000.00', got None`
- `0300.delta: expected '0.00', got None`
- `0300.status: expected 'MATCH', got 'INSUFFICIENT_DATA'`
- `0800.expected: expected '25000.00', got None`
- `0800.delta: expected '0.00', got None`
- `0800.status: expected 'MATCH', got 'INSUFFICIENT_DATA'`
- `0900.expected: expected '12000.00', got None`
- `0900.delta: expected '0.00', got None`
- `0900.status: expected 'MATCH', got 'INSUFFICIENT_DATA'`
- `total.expected: expected '180000.00', got None`
- `total.delta: expected '0.00', got None`
- `total.status: expected 'MATCH', got 'INSUFFICIENT_DATA'`

### 21_text_typed_money

XLSX-парсер принимает только числовой тип ячеек.

Отличия от эталона:

- `0200.expected: expected '110000.00', got None`
- `0200.delta: expected '0.00', got None`
- `0200.status: expected 'MATCH', got 'INSUFFICIENT_DATA'`
- `0300.expected: expected '33000.00', got None`
- `0300.delta: expected '0.00', got None`
- `0300.status: expected 'MATCH', got 'INSUFFICIENT_DATA'`
- `0800.expected: expected '25000.00', got None`
- `0800.delta: expected '0.00', got None`
- `0800.status: expected 'MATCH', got 'INSUFFICIENT_DATA'`
- `0900.expected: expected '12000.00', got None`
- `0900.delta: expected '0.00', got None`
- `0900.status: expected 'MATCH', got 'INSUFFICIENT_DATA'`
- `total.expected: expected '180000.00', got None`
- `total.delta: expected '0.00', got None`
- `total.status: expected 'MATCH', got 'INSUFFICIENT_DATA'`

### 22_overlapping_service_period

Извлечение периода пока не читает интервалы с двумя календарными датами.

Отличия от эталона:

- `0200.expected: expected None, got '110000.00'`
- `0200.delta: expected None, got '0.00'`
- `0200.status: expected 'INSUFFICIENT_DATA', got 'MATCH'`
- `0300.expected: expected None, got '33000.00'`
- `0300.delta: expected None, got '0.00'`
- `0300.status: expected 'INSUFFICIENT_DATA', got 'MATCH'`
- `0800.expected: expected None, got '26000.00'`
- `0800.delta: expected None, got '-1000.00'`
- `0800.status: expected 'INSUFFICIENT_DATA', got 'MISMATCH'`
- `0900.expected: expected None, got '12000.00'`
- `0900.delta: expected None, got '0.00'`
- `0900.status: expected 'INSUFFICIENT_DATA', got 'MATCH'`
- `total.expected: expected None, got '181000.00'`
- `total.delta: expected None, got '-1000.00'`
- `total.status: expected 'INSUFFICIENT_DATA', got 'MISMATCH'`
- `PERIOD_OVERLAP: expected 1, got 0`

### 23_other_contract_sheet

Парсер объединяет строки всех листов под реквизитами первого листа.

Отличия от эталона:

- `0200.expected: expected '110000.00', got '1110000.00'`
- `0200.delta: expected '0.00', got '-1000000.00'`
- `0200.status: expected 'MATCH', got 'MISMATCH'`
- `total.expected: expected '180000.00', got '1180000.00'`
- `total.delta: expected '0.00', got '-1000000.00'`
- `total.status: expected 'MATCH', got 'MISMATCH'`

### 24_formula_error

XLSX-парсер пока пропускает формулы в строках начислений.

Отличия от эталона:

- `0200.expected: expected None, got '10000.00'`
- `0200.delta: expected None, got '100000.00'`
- `0200.status: expected 'INSUFFICIENT_DATA', got 'MISMATCH'`
- `0300.expected: expected None, got '33000.00'`
- `0300.delta: expected None, got '0.00'`
- `0300.status: expected 'INSUFFICIENT_DATA', got 'MATCH'`
- `0800.expected: expected None, got '25000.00'`
- `0800.delta: expected None, got '0.00'`
- `0800.status: expected 'INSUFFICIENT_DATA', got 'MATCH'`
- `0900.expected: expected None, got '12000.00'`
- `0900.delta: expected None, got '0.00'`
- `0900.status: expected 'INSUFFICIENT_DATA', got 'MATCH'`
- `total.expected: expected None, got '80000.00'`
- `total.delta: expected None, got '100000.00'`
- `total.status: expected 'INSUFFICIENT_DATA', got 'MISMATCH'`

## Исправления, выявленные новым набором

- Допустимые XLSX без сохранённого `<dimension>` теперь читаются: размер вычисляется перед проверкой лимитов.
- В ячейках текстовых PDF сначала читаются исходные глифы. Это устранило ошибку OCR 50 000 → 90 000. Для сканов сохраняется OCR.

Исходный комплект из `task/data` продолжает проходить регрессионные тесты.
