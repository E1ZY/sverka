"""Deterministic KФЗ images for OCR diagnostics, separate from reconciliation fixtures."""
import argparse
import hashlib
import io
import json
import shutil
from decimal import Decimal
from pathlib import Path

import pymupdf
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / 'cases' / 'ocr'
GROUPS = {
    '0400_0700': ['0400', '0500', '0600', '0700'],
    '1000_1300': ['1000', '1100', '1200', '1300'],
    '1300_13000': ['1300', '13000'],
    'leading_zeros': ['0400', '400', '0700', '700', '1300', '13000'],
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def font_path():
    for path in [Path('C:/Windows/Fonts/arial.ttf'), Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')]:
        if path.is_file():
            return path
    raise RuntimeError('Arial or DejaVu Sans is required to generate Cyrillic test documents.')


def draw_report(codes, variant):
    doc = pymupdf.open()
    page = doc.new_page(width=1190, height=842)
    page.insert_font(fontname='fixture', fontfile=str(font_path()))
    def text(x, y, value, size=12):
        page.insert_text((x, y), value, fontsize=size, fontname='fixture')
    text(40, 60, 'КАРТОЧКА УЧЁТА ФАКТИЧЕСКИХ ЗАТРАТ', 20)
    text(40, 95, 'Договор: 26/01/01-77')
    text(40, 118, 'Этап: 3. Проверяемый период: 01.01.2026 - 31.01.2026')
    text(40, 145, 'Исполнитель: Тестовый исполнитель. Заказчик: Тестовый заказчик.')
    text(40, 176, 'Суммы указаны в рублях. Коды категорий напечатаны в заголовках таблицы.')
    left, right, top, header_height, row_height = 40, 1150, 220, 60, 40
    xs = [left, left+120, left+210]
    cell_width = (right-xs[-1])/(len(codes)+1)
    xs += [xs[-1]+cell_width*index for index in range(1, len(codes)+2)]
    ys = [top, top+header_height] + [top+header_height+row_height*index for index in range(1,4)]
    page.draw_rect(pymupdf.Rect(left, top, right, top+header_height), color=None, fill=(.93,.95,.97))
    for x in xs:
        page.draw_line((x,ys[0]),(x,ys[-1]),color=(0,0,0),width=.7)
    for y in ys:
        page.draw_line((left,y),(right,y),color=(0,0,0),width=.7)
    for index, label in enumerate(['Этап','Год',*codes,'Итого']):
        text(xs[index]+8, top+36, label, 14)
    current = [Decimal(variant*10000 + (index+1)*1000) + Decimal(index+1)/100 for index in range(len(codes))]
    previous = [Decimal((index+1)*100) + Decimal(index+1)/100 for index in range(len(codes))]
    total = [a+b for a,b in zip(current,previous)]
    for index,(label,year,values) in enumerate([('3 этап','2025',previous),('3 этап','2026',current),('Всего 3 этап','',total)]):
        y=ys[index+1]+26
        text(xs[0]+8,y,label,11)
        text(xs[1]+8,y,year,11)
        for column,value in enumerate([*values,sum(values)],2):
            text(xs[column]+8,y,f'{value:,.2f}'.replace(',',' ').replace('.',','),11)
    text(40, 475, 'Синтетическая форма для проверки OCR. Не является бухгалтерским документом.', 11)
    regions = {'codes': [xs[2]/1190, ys[0]/842, xs[-2]/1190, ys[1]/842],
               'current_values': [xs[2]/1190, ys[2]/842, xs[-1]/1190, ys[3]/842]}
    expected = {'codes': codes, 'values': [str(value) for value in current],
                'total': str(sum(current)), 'contract': '26/01/01-77', 'year': 2026}
    doc.set_metadata({'title':'Synthetic KФЗ OCR test', 'author':'Sverka fixtures',
                      'creationDate':'D:20260101000000Z', 'modDate':'D:20260101000000Z'})
    return doc, regions, expected


def generate(output=OUTPUT, reduced_source=None):
    output = Path(output)
    output.mkdir(parents=True,exist_ok=True)
    cases = []
    for variant,(group,codes) in enumerate(GROUPS.items(),1):
        document, regions, expected = draw_report(codes,variant)
        for quality,scale in [('clear',1.7),('reduced',1.)]:
            case_id=f'{group}_{quality}'
            folder=output/case_id
            folder.mkdir(exist_ok=True)
            document.save(folder/'source.pdf', no_new_id=True, deflate=True)
            pix=document[0].get_pixmap(matrix=pymupdf.Matrix(scale,scale),alpha=False)
            image=Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
            if quality=='reduced':
                image=image.filter(ImageFilter.GaussianBlur(.45))
                image.save(folder/'report.jpeg',quality=25,subsampling=2,optimize=False)
                input_path=folder/'report.jpeg'
            else:
                image.save(folder/'report.png')
                input_path=folder/'report.png'
            manifest={'id':case_id,'kind':'synthetic','input':input_path.name,'sha256':sha(input_path),
                      'quality':quality,'size':image.size,'regions':regions}
            write_json(folder/'case.json',manifest)
            write_json(folder/'expected.json',expected)
            cases.append({'id':case_id,'manifest':f'{case_id}/case.json'})
        document.close()
    if reduced_source is not None:
        folder=output/'real_kfz_reduced_quality'
        folder.mkdir(exist_ok=True)
        target=folder/'report.jpeg'
        shutil.copyfile(reduced_source,target)
        with Image.open(target) as image:
            size=image.size
        expected=json.loads((ROOT/'demo/expected.json').read_text(encoding='utf-8'))
        amounts={code:value['actual'] for code,value in expected['metrics'].items()}
        write_json(folder/'case.json',{'id':folder.name,'kind':'real_reduced','input':target.name,
                   'sha256':sha(target),'quality':'user_supplied_reduced','size':size,
                   'source_name':Path(reduced_source).name,
                   'context':{'contract':'24/03/15-01','stage':3,'period_start':'2026-01-01',
                              'period_end':'2026-05-31','row_label':'3 этап, 2026 г.','complete_package':True}})
        write_json(folder/'expected.json',{'codes':['0200','0300','0800','0900'],
                   'values':[value for code,value in amounts.items() if code!='total'],
                   'total':amounts['total'],'report_values':amounts,'contract':'24/03/15-01','year':2026})
        cases.insert(0,{'id':folder.name,'manifest':f'{folder.name}/case.json'})
    elif (output/'real_kfz_reduced_quality/case.json').is_file():
        cases.insert(0,{'id':'real_kfz_reduced_quality','manifest':'real_kfz_reduced_quality/case.json'})
    write_json(output/'catalog.json',{'schema_version':1,'purpose':'OCR recognition only; no reconciliation-category support is implied','cases':cases})
    return cases


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reduced-source',type=Path)
    parser.add_argument('--output',type=Path,default=OUTPUT)
    args=parser.parse_args()
    for case in generate(args.output,args.reduced_source):
        print(case['id'])


if __name__=='__main__':
    main()
