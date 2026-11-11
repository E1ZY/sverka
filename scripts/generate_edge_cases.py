"""Build synthetic, self-contained reconciliation inputs; never reads task/data.

XLSX files are copied from templates authored with generate_edge_workbooks.mjs.
Only intentional corruptions (stale cache, formula error, invalid ZIP) patch OOXML.
No application parser or reconciliation rule is imported to construct the oracle.
"""
import argparse
import copy
import hashlib
import io
import json
import os
import shutil
import textwrap
import zipfile
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4, A3, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT/'cases'
TEMPLATES = CASES/'templates'
OUTPUT = CASES/'generated'
CONTRACT = '26/01/01-77'
OTHER_CONTRACT = '26/02/02-99'
CODES = ['0200', '0300', '0800', '0900', 'total']
BASE = {'0200':'110000.00', '0300':'33000.00', '0800':'25000.00', '0900':'12000.00'}
CONTEXT = {'contract':CONTRACT, 'stage':3, 'period_start':'2026-01-01', 'period_end':'2026-01-31', 'row_label':'3 этап, 2026 г.', 'complete_package':True}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def amount(value):
    return f'{Decimal(value):,.2f}'.replace(',', ' ').replace('.', ',')


def register_fonts():
    candidates = [Path(os.environ.get('EDGE_FONT_DIR', 'C:/Windows/Fonts')), Path('/usr/share/fonts/truetype/dejavu')]
    for directory in candidates:
        regular = directory/('arial.ttf' if (directory/'arial.ttf').exists() else 'DejaVuSans.ttf')
        bold = directory/('arialbd.ttf' if (directory/'arialbd.ttf').exists() else 'DejaVuSans-Bold.ttf')
        if regular.exists() and bold.exists():
            pdfmetrics.registerFont(TTFont('Fixture', str(regular)))
            pdfmetrics.registerFont(TTFont('FixtureBold', str(bold)))
            return
    raise RuntimeError('Set EDGE_FONT_DIR to a directory containing Arial or DejaVuSans regular/bold fonts')


def draw_lines(c, lines, x, y, width, size=11, leading=20):
    c.setFont('Fixture', size)
    for line in lines:
        words, current = line.split(), ''
        wrapped = []
        for word in words:
            candidate = (current+' '+word).strip()
            if pdfmetrics.stringWidth(candidate, 'Fixture', size) > width and current:
                wrapped.append(current)
                current = word
            else:
                current = candidate
        wrapped.append(current)
        for part in wrapped:
            c.drawString(x, y, part)
            y -= leading
        y -= 7
    return y


def act(path, *, number='PROD-001', date='01.01.2026', contract=CONTRACT,
        provider='OOO TestLab', value='25000.00', article='0800', description=None,
        extra=None, variant='A'):
    c = canvas.Canvas(str(path), pagesize=A4, invariant=True)
    c.setTitle(f'Синтетический акт {number}')
    c.setAuthor('Sverka test fixtures')
    c.setSubject(f'Fixture revision {variant}')
    c.setFont('FixtureBold', 19)
    c.drawString(48, 780, f'АКТ № {number}')
    lines = [f'Дата: {date}']
    if contract is not None:
        lines.append(f'Договор: {contract}')
    lines += [f'Исполнитель: {provider}', 'Заказчик: OOO TestCustomer']
    if description is None:
        description = 'Обслуживание оборудования производственного назначения.' if article == '0800' else 'Административное сопровождение договора и документооборот.'
    lines.append(description)
    if extra:
        lines.extend(extra)
    if value is not None:
        lines.append(f'Итого к оплате: {amount(value)} руб.')
    draw_lines(c, lines, 48, 735, A4[0]-96)
    c.setFont('Fixture', 8)
    c.drawString(48, 45, 'Синтетический документ для тестирования. Все организации и операции вымышлены.')
    c.save()


def report(path, values, case_id, *, contract=CONTRACT, stage=3):
    width, height = landscape(A3)
    c = canvas.Canvas(str(path), pagesize=(width,height), invariant=True)
    c.setTitle('Карточка учёта фактических затрат')
    c.setAuthor('Sverka test fixtures')
    c.setFont('FixtureBold', 19)
    c.drawString(40, height-60, 'КАРТОЧКА УЧЁТА ФАКТИЧЕСКИХ ЗАТРАТ')
    c.setFont('Fixture', 12)
    c.drawString(40, height-95, f'Договор: {contract}')
    c.drawString(40, height-118, 'Период подтверждающих документов: январь 2026 года')
    c.drawString(40, height-141, f'Номер карточки: EC-{case_id}')
    c.setFont('Fixture', 10)
    c.drawString(40, height-185, 'Денежные показатели в рублях. Проверяемая строка - этап и год, указанные в таблице.')
    table_top = height-245
    widths = [145, 60]+[(width-80-205)/15]*15
    xs = [40]
    for cell_width in widths:
        xs.append(xs[-1]+cell_width)
    row_heights = [88,18,24,24,24]
    ys = [table_top]
    for row_height in row_heights:
        ys.append(ys[-1]-row_height)
    labels = ['Этап','Период','Трудо-\nёмкость','Материалы','Оплата труда\n0200','Зарплата\nвсего','Основная\nзарплата','Доплаты','Резервы','Взносы\n0300','Взносы\nвсего','Основные\nвзносы','Доп.\nвзносы','Резервы\nвзносов','Производство\n0800','Управление\n0900','Итого']
    c.setFillColorRGB(.94,.96,.98)
    c.rect(xs[0],ys[1],xs[-1]-xs[0],row_heights[0],fill=1,stroke=0)
    c.setFillColorRGB(0,0,0)
    c.setLineWidth(.65)
    for x in xs:
        c.line(x,ys[-1],x,ys[0])
    for y in ys:
        c.line(xs[0],y,xs[-1],y)
    for i,label in enumerate(labels):
        c.setFont('FixtureBold',7.2)
        for j,line in enumerate(label.split('\n')):
            assert pdfmetrics.stringWidth(line,'FixtureBold',7.2) <= widths[i]-3, (case_id,line)
            c.drawCentredString((xs[i]+xs[i+1])/2,ys[0]-32-j*12,line)
    c.setFont('Fixture',8)
    for i in range(17):
        c.drawCentredString((xs[i]+xs[i+1])/2,ys[1]-12,str(i+1))
    actual = [f'{stage} этап, 2026 г.','Январь','1,00','0,00',amount(values['0200']),amount(values['0200']),amount(values['0200']),'0,00','0,00',amount(values['0300']),amount(values['0300']),amount(values['0300']),'0,00','0,00',amount(values['0800']),amount(values['0900']),amount(values['total'])]
    reference = ['2 этап, 2025 г.','Декабрь']+['0,00']*15
    total = ['ВСЕГО 3 этап','']+actual[2:]
    for row_no,row in enumerate([reference,actual,total],2):
        baseline = ys[row_no]-16
        c.setFont('FixtureBold' if row_no==3 else 'Fixture',8.8)
        for i,text in enumerate(row):
            font = 'FixtureBold' if row_no==3 else 'Fixture'
            assert pdfmetrics.stringWidth(text,font,8.8) <= widths[i]-5, (case_id,text)
            if i < 2:
                c.drawString(xs[i]+4,baseline,text)
            else:
                c.drawRightString(xs[i+1]-4,baseline,text)
    c.setFont('Fixture',9)
    c.drawString(40,ys[-1]-55,'Синтетический отчёт для проверки программного обеспечения.')
    c.drawString(40,ys[-1]-74,'Все подтверждающие документы комплекта перечислены в case.json.')
    c.save()


def patch_xlsx(path, address, *, formula=None, cached_value=None, remove_cache=False):
    """Deliberate negative OOXML mutation; ordinary authoring uses Artifact Tool."""
    ns = {'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    source = io.BytesIO(path.read_bytes())
    out = io.BytesIO()
    with zipfile.ZipFile(source) as zin, zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename=='xl/worksheets/sheet1.xml':
                xml = ET.fromstring(data)
                cell = xml.find(f'.//s:c[@r="{address}"]',ns)
                if cell is None:
                    raise ValueError(f'No fixture cell {address}')
                if formula is not None:
                    cell.attrib.pop('t',None)
                    f = cell.find('s:f',ns)
                    if f is None:
                        f = ET.SubElement(cell,'{'+ns['s']+'}f')
                    f.text = formula
                v = cell.find('s:v',ns)
                if remove_cache and v is not None:
                    cell.remove(v)
                elif cached_value is not None:
                    if v is None:
                        v = ET.SubElement(cell,'{'+ns['s']+'}v')
                    v.text = str(cached_value)
                data = ET.tostring(xml,encoding='utf-8',xml_declaration=True)
            zout.writestr(item,data)
    path.write_bytes(out.getvalue())


def make_spec(case_id,title,description,*,unknown=(),findings=None,limitation=None,**options):
    return {'id':case_id,'title':title,'description':description,'unknown':list(unknown),
            'findings':findings or {},'known_limitation':limitation,'options':options}


ALL = CODES
SPECS = [
    make_spec('00_clean','Полностью корректный комплект','Четыре статьи и итог совпадают. Контрольная точка для всех остальных сценариев.'),
    make_spec('01_overstatement','Завышена статья 0800','В отчёте производственные расходы завышены на 12 500,00 руб.',over='0800',change='12500.00'),
    make_spec('02_understatement','Занижена статья 0900','Отрицательная дельта: в отчёте не хватает 1 000,01 руб.',over='0900',change='-1000.01'),
    make_spec('03_pennies','Копейки в каждом источнике','Проверка точной десятичной агрегации без потери копеек.',pennies=True),
    make_spec('04_byte_duplicate','Байтовая копия с другим именем','Повторный файл должен учитываться один раз.',findings={'DUPLICATE':1},duplicate='bytes'),
    make_spec('05_semantic_duplicate','Пересохранённый дубликат','PDF отличается байтами и метаданными, но реквизиты и сумма совпадают.',findings={'DUPLICATE':1},duplicate='semantic'),
    make_spec('06_conflicting_revision','Конфликт версий акта','Совпадают номер, дата, договор и контрагент; суммы 25 000 и 26 000 руб.',unknown=ALL,findings={'CONFLICTING_DOCUMENT':1},conflict=True),
    make_spec('07_same_number_other_vendor','Одинаковый номер у разных контрагентов','Две реальные операции по 25 000 руб. Дубликата нет.',second_vendor=True),
    make_spec('08_wrong_contract','Документ другого договора','Дополнительный акт на 99 999 руб. не относится к договору проверки.',findings={'WRONG_CONTRACT':1},wrong_contract=True),
    make_spec('09_period_boundaries','Включительные границы периода','Акты 01.01 и 31.01 учитываются; 31.12 и 01.02 исключаются.',findings={'OUT_OF_PERIOD':2},boundaries=True),
    make_spec('10_missing_payroll','Нет ведомости за январь','Ожидаемая зарплата и общий итог неизвестны; отсутствие файла не равно нулю.',unknown=['0200','total'],findings={'MISSING_DOCUMENT':1},missing_payroll=True),
    make_spec('11_missing_contract','В акте нет договора','Документ с суммой, но без номера договора нельзя автоматически включить.',unknown=ALL,findings={'MISSING_FIELDS':1},missing_contract=True),
    make_spec('12_missing_amount','В акте нет суммы','Пропущена сумма первичного документа. Нельзя трактовать её как 0,00.',unknown=ALL,findings={'MISSING_FIELDS':1},missing_amount=True),
    make_spec('13_ambiguous_article','Неоднозначное назначение','В одной операции одновременно указаны производственное и административное назначения.',unknown=ALL,findings={'AMBIGUOUS_LINK':1},ambiguous=True),
    make_spec('14_corrupt_pdf','Повреждённый PDF','Неверное содержимое файла с расширением PDF не должно приводить к падению всей проверки.',unknown=ALL,findings={'EXTRACTION_ERROR':1},corrupt_pdf=True),
    make_spec('15_report_arithmetic','Ошибка только в общем итоге','Верхние статьи верны, но итог отчёта завышен на 0,01 руб.',findings={'REPORT_ARITHMETIC':1},total_change='0.01'),
    make_spec('16_report_contract','Другой договор в КФЗ','Отчёт относится к другому договору, первичные документы - к выбранному.',unknown=ALL,report_contract=OTHER_CONTRACT),
    make_spec('17_real_zeros','Подтверждённые нулевые суммы','Нулевые значения присутствуют в документах и подтверждаются полным комплектом.',zeros=True),
    make_spec('18_credit_adjustment','Отрицательная корректировка','К производственным затратам добавлен отдельный корректировочный акт на -500,00 руб.',credit=True),
    make_spec('19_incomplete_package','Комплект не заявлен полным','Даже совпавшие суммы остаются частичным подтверждением.',unknown=ALL,incomplete=True),
    make_spec('20_vat_components','Стоимость без НДС и итог','Нужно взять итог 25 000,00 руб., а не сумму без НДС или сам НДС.',limitation='Парсер пока не различает роль денежных полей в многострочном счёте.',vat=True),
    make_spec('21_text_typed_money','Суммы Excel записаны текстом','Значения 100000,00 и 10000,00 заданы строками; ожидается явная нормализация денежных полей.',limitation='XLSX-парсер принимает только числовой тип ячеек.',text_money=True),
    make_spec('22_overlapping_service_period','Период услуг пересекает границу','Дата акта внутри января, но услуги оказаны 20.12.2025-10.01.2026. Требуется распределение.',unknown=ALL,findings={'PERIOD_OVERLAP':1},limitation='Извлечение периода пока не читает интервалы с двумя календарными датами.',overlap=True),
    make_spec('23_other_contract_sheet','Другой договор на втором листе','Второй лист ведомости явно относится к другому договору; его миллион нельзя добавлять к зарплате.',limitation='Парсер объединяет строки всех листов под реквизитами первого листа.',mixed_sheets=True),
    make_spec('24_formula_error','Ошибка формулы в начислении','C6 содержит =1/0. Неисправное слагаемое нельзя молча пропускать.',unknown=ALL,limitation='XLSX-парсер пока пропускает формулы в строках начислений.',formula_error=True),
    make_spec('25_stale_formula_cache','Устаревший кеш итога Excel','В C8 намеренно записан неверный кеш 999999999. Исходные начисления дают 110 000 руб.',stale_cache=True),
    make_spec('26_png_scan','Первичка в виде PNG-скана','Производственный акт представлен только изображением; сумма и реквизиты должны распознаться.',scan=True),
    make_spec('27_wrong_report_row','В отчёте отсутствует нужная строка','В КФЗ указан этап 4, а проверяется этап 3. Система должна явно отказаться от подстановки другой строки.',unknown=ALL,report_stage=4,report_error=True),
    make_spec('28_corrupt_xlsx_upload','Повреждённый XLSX при загрузке','Файл не является ZIP-контейнером. API должен отклонить пакет первички с HTTP 400.',reject_upload=400),
    make_spec('29_duplicate_month','Две ведомости за один месяц','Разные номера документов за январь. Нельзя автоматически суммировать два сводных расчёта.',unknown=['0200','total'],second_payroll=True),
]


def build_case(spec):
    directory = OUTPUT/spec['id']
    primary = directory/'input'/'primary'
    primary.mkdir(parents=True,exist_ok=True)
    # Re-run only overwrites files previously produced by this generator.
    old_manifest = directory/'case.json'
    if old_manifest.exists():
        old = json.loads(old_manifest.read_text(encoding='utf-8'))
        for item in old['files']:
            target = (directory/item['path']).resolve()
            if not target.is_relative_to(directory.resolve()):
                raise ValueError('Fixture manifest path escapes case directory')
            target.unlink(missing_ok=True)
    options = spec['options']
    context = {**CONTEXT,'complete_package':not options.get('incomplete',False)}
    expected = copy.deepcopy(BASE)
    if options.get('pennies'):
        expected = {'0200':'110000.03','0300':'33000.01','0800':'25000.02','0900':'12000.03'}
    if options.get('zeros'):
        expected = dict.fromkeys(BASE,'0.00')
    suffix = '_pennies' if options.get('pennies') else '_zero' if options.get('zeros') else ''
    payroll_template = 'payroll'+suffix
    if options.get('text_money'):
        payroll_template = 'payroll_text'
    if options.get('mixed_sheets'):
        payroll_template = 'payroll_mixed_sheets'
    if not options.get('missing_payroll'):
        shutil.copyfile(TEMPLATES/(payroll_template+'.xlsx'),primary/'payroll.xlsx')
    shutil.copyfile(TEMPLATES/('insurance'+suffix+'.xlsx'),primary/'insurance.xlsx')
    act(primary/'production.pdf',value=expected['0800'])
    act(primary/'administration.pdf',number='ADM-001',date='31.01.2026',provider='OOO TestOffice',article='0900',value=expected['0900'])
    if options.get('duplicate')=='bytes':
        shutil.copyfile(primary/'production.pdf',primary/'renamed_copy.pdf')
    if options.get('duplicate')=='semantic':
        act(primary/'resaved_copy.pdf',variant='B')
        assert hashlib.sha256((primary/'production.pdf').read_bytes()).digest()!=hashlib.sha256((primary/'resaved_copy.pdf').read_bytes()).digest()
    if options.get('conflict'):
        act(primary/'conflicting_revision.pdf',value='26000.00')
    if options.get('second_vendor'):
        act(primary/'another_vendor.pdf',provider='OOO OtherLab')
        expected['0800']='50000.00'
    if options.get('wrong_contract'):
        act(primary/'foreign_contract.pdf',number='FOREIGN-001',contract=OTHER_CONTRACT,value='99999.00')
    if options.get('boundaries'):
        act(primary/'before_period.pdf',number='BEFORE-001',date='31.12.2025',value='999.00')
        act(primary/'after_period.pdf',number='AFTER-001',date='01.02.2026',value='999.00')
    if options.get('missing_contract'):
        act(primary/'without_contract.pdf',number='NOCONTRACT-001',contract=None)
    if options.get('missing_amount'):
        act(primary/'without_amount.pdf',number='NOAMOUNT-001',value=None)
    if options.get('ambiguous'):
        act(primary/'unclear_purpose.pdf',number='AMBIG-001',description='Производственное обслуживание и административное сопровождение.')
    if options.get('corrupt_pdf'):
        (primary/'broken.pdf').write_bytes(b'%PDF-1.7\nINTENTIONALLY TRUNCATED TEST FILE\n')
    if options.get('credit'):
        act(primary/'credit.pdf',number='CORR-001',value='-500.00')
        expected['0800']='24500.00'
    if options.get('vat'):
        act(primary/'production.pdf',extra=['Сумма без НДС: 20 833,33 руб.','Сумма НДС: 4 166,67 руб.'])
    if options.get('overlap'):
        act(primary/'cross_period.pdf',number='CROSS-001',date='31.01.2026',value='1000.00',extra=['Период услуг: 20.12.2025 - 10.01.2026.'])
    if options.get('formula_error'):
        patch_xlsx(primary/'payroll.xlsx','C6',formula='1/0',remove_cache=True)
    if options.get('stale_cache'):
        patch_xlsx(primary/'payroll.xlsx','C8',cached_value='999999999')
    if options.get('second_payroll'):
        shutil.copyfile(TEMPLATES/'payroll_second.xlsx',primary/'payroll_second.xlsx')
    if options.get('scan'):
        import subprocess
        poppler = shutil.which('pdftoppm')
        if not poppler:
            raise RuntimeError('pdftoppm is required to generate the PNG scan fixture')
        subprocess.run([poppler,'-f','1','-singlefile','-r','180','-png',str(primary/'production.pdf'),str(primary/'production_scan')],check=True,capture_output=True)
        (primary/'production.pdf').unlink()
    if options.get('reject_upload'):
        (primary/'broken.xlsx').write_bytes(b'INTENTIONAL INVALID XLSX - NOT A ZIP ARCHIVE')
    reported = copy.deepcopy(expected)
    if options.get('over'):
        code = options['over']
        reported[code]=str(Decimal(reported[code])+Decimal(options['change']))
    reported['total']=str(sum(map(Decimal,reported.values())))
    if options.get('total_change'):
        reported['total']=str(Decimal(reported['total'])+Decimal(options['total_change']))
    expected['total']=str(sum(map(Decimal,expected.values())))
    report(directory/'input'/'report.pdf',reported,spec['id'],contract=options.get('report_contract',CONTRACT),stage=options.get('report_stage',3))
    metrics = {}
    for code in CODES:
        actual = None if options.get('report_error') else f'{Decimal(reported[code]):.2f}'
        exp = None if code in spec['unknown'] else f'{Decimal(expected[code]):.2f}'
        delta = f'{Decimal(actual)-Decimal(exp):.2f}' if actual is not None and exp is not None else None
        metrics[code]={'actual':actual,'expected':exp,'delta':delta,'status':'INSUFFICIENT_DATA' if exp is None else 'MATCH' if Decimal(delta)==0 else 'MISMATCH'}
    oracle = {'metrics':metrics,'required_findings':spec['findings'],
              'exact_findings':not bool(spec['known_limitation']), 'report_extraction_error':bool(options.get('report_error')),
              'upload_status':options.get('reject_upload',201)}
    write_json(directory/'expected.json',oracle)
    files = [{'role':'report','path':'input/report.pdf'}]+[{'role':'primary','path':p.relative_to(directory).as_posix()} for p in sorted(primary.iterdir()) if p.is_file()]
    for item in files:
        item['sha256']=hashlib.sha256((directory/item['path']).read_bytes()).hexdigest()
    manifest={'schema_version':1,'id':spec['id'],'title':spec['title'],'description':spec['description'],
              'synthetic':True,'context':context,'known_limitation':spec['known_limitation'],'files':files}
    write_json(directory/'case.json',manifest)
    rows='\n'.join(f'| {code} | {m["actual"] or "не извлечено"} | {m["expected"] or "недостаточно данных"} | {m["delta"] or "—"} | {m["status"]} |' for code,m in metrics.items())
    text=f'''# {spec['title']}

{spec['description']}

Синтетический комплект. Источники исходного задания не используются.

## Загрузка в Сверку

1. Создайте новую проверку. Договор `{CONTRACT}`, этап 3, период 01.01.2026–31.01.2026.
2. Полнота комплекта: **{'подтверждена' if context['complete_package'] else 'не подтверждена'}**.
3. В итоговый отчёт загрузите `input/report.pdf`.
4. В первичные документы загрузите все файлы из `input/primary/`.
5. `case.json`, `expected.json` и этот README в приложение не загружайте.

## Ожидаемое поведение

| Код | В отчёте | Ожидается | Дельта | Статус |
|---|---:|---:|---:|---|
{rows}

Обязательные замечания: `{json.dumps(spec['findings'],ensure_ascii=False)}`.
'''
    if options.get('reject_upload'):
        text+='\n**Проверка загрузки:** пакет первичных документов должен быть отклонён с HTTP 400. До расчёта система не должна доходить. Таблица выше задаёт контрольные суммы валидной части.\n'
    if spec['known_limitation']:
        text+='\n**Известное ограничение текущего MVP:** '+spec['known_limitation']+' Эталон описывает желаемое поведение; текущая реализация может ему не соответствовать.\n'
    (directory/'README.md').write_text(text,encoding='utf-8')
    return {'id':spec['id'],'title':spec['title'],'description':spec['description'],'known_limitation':spec['known_limitation'],
            'manifest':f'generated/{spec["id"]}/case.json','input_files':len(files)}


def make_archive():
    with zipfile.ZipFile(CASES/'generated-cases.zip','w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in sorted(OUTPUT.rglob('*')):
            if path.is_file():
                info=zipfile.ZipInfo(path.relative_to(CASES).as_posix(),date_time=(2026,1,1,0,0,0))
                info.compress_type=zipfile.ZIP_DEFLATED
                archive.writestr(info,path.read_bytes())
        for name in ['README.md','catalog.json','VALIDATION.md']:
            path=CASES/name
            if path.exists():
                info=zipfile.ZipInfo(name,date_time=(2026,1,1,0,0,0))
                info.compress_type=zipfile.ZIP_DEFLATED
                archive.writestr(info,path.read_bytes())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only',help='Generate only one case ID (useful when developing a fixture)')
    args=parser.parse_args()
    register_fonts()
    chosen=[s for s in SPECS if args.only is None or s['id']==args.only]
    if not chosen:
        parser.error('Unknown case ID')
    items=[]
    for spec in chosen:
        items.append(build_case(spec))
        print(spec['id'],flush=True)
    if args.only is None:
        write_json(CASES/'catalog.json',{'schema_version':1,'cases':items})
        make_archive()
        print(f'Generated {len(items)} cases / {sum(i["input_files"] for i in items)} input files')


if __name__=='__main__':
    main()
