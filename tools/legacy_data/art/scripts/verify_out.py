"""verify_out.py OUTDIR [--game legacy] — сверка собранного арта логотипов с шаблонами игры: всё, кроме пикселей
(и имён растров), совпадает; у .rx2 — раскладка и мипы (teamart.roundtrip --deep). Копия
game/work/logos/scripts/verify_out.py с выбором игры; файлы формы (jersey/pant/sock/jerseys) — kitpaint verify."""
import os, re, sys
TOOLS = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))   # → tools
sys.path.insert(0, TOOLS)
import teamart as ta

game, argv = ta.split_game(sys.argv[1:])
ta.set_game(game)
out = argv[0]
bad = n = 0
for dp, _, fs in os.walk(out):
    for f in sorted(fs):
        path = os.path.join(dp, f)
        rel = os.path.relpath(path, out).replace('\\', '/')
        if not (('/teamlogos' in rel) or any(v[0].split('{}')[0] in rel for v in ta.RX_SETS.values())):
            continue                                       # форма — не здесь
        n += 1
        data = open(path, 'rb').read()
        try:
            if rel.startswith('fe/'):
                kind = next(k for k, (folder, letter) in ta.UI_SETS.items() if f'/{folder}/' in rel)
                tpl = ta.UiLogo.load(ta.ui_template(kind))
                obj = ta.UiLogo(data, path)
                same = [nm for (nm, b), (m, c) in zip(obj.head.big.entries, tpl.head.big.entries)
                        if nm == m and nm != obj.head.tex_name and b == c]
                others = [nm for nm, _ in tpl.head.big.entries if nm != tpl.head.tex_name]
                ok = (len(same) == len(others) and obj.head.tex.header == tpl.head.tex.header
                      and obj.head.big.tag == tpl.head.big.tag and obj.stage == tpl.stage
                      and obj.fetch.words == tpl.fetch.words)
                w, h, rgba = obj.decode()
                cover = sum(1 for a in rgba[3::4] if a) / (w * h)
                _, rt = ta.roundtrip(path, deep=True)
                ok = ok and all(v for k, v in rt.items() if not k.endswith(':mips_psnr'))
                print(f"{'OK ' if ok else 'ОШИБКА'} {rel}: {len(data)} байт, шаблон {os.path.relpath(ta.ui_template(kind), ta.GAME.game)}, "
                      f"сцена {obj.stage}, непрозрачно {cover:.0%}, разбор/сборка {rt}")
            else:
                key = next(k for k, v in ta.RX_SETS.items() if v[0].split('{}')[0] in rel)
                num0 = int(re.search(r'_(\d+)(?:_cm)?\.rx2$', rel).group(1))
                tpl_rel, tpl_num = ta.rx_template(key, num0)
                tpl = ta.Rw4.load(ta.extracted(tpl_rel))
                obj = ta.Rw4(data, path)
                t0, t1 = tpl.textures[0], obj.textures[0]
                a, b = bytearray(tpl.raw), bytearray(obj.raw)
                for x in (a, b):                      # пиксели и имена не сравниваются
                    x[t0.data_off:t0.data_off + t0.size] = bytes(t0.size)
                for (sp, ln) in tpl.name_slots:
                    a[sp:sp + ln] = bytes(ln)
                    b[sp:sp + ln] = bytes(ln)
                num = re.search(r'_(\d+)(?:_cm)?\.rx2$', rel).group(1)
                names_ok = all(re.search(r'(?<!\d)' + num + r'(?!\d)', t.name) for t in obj.textures)
                _, rt = ta.roundtrip(path, deep=True)
                lay = all(v for k, v in rt.items() if not k.endswith(':mips_psnr'))
                psnr = [v for k, v in rt.items() if k.endswith(':mips_psnr')]
                ok = a == b and len(data) == len(tpl.raw) and names_ok and lay
                print(f"{'OK ' if ok else 'ОШИБКА'} {rel}: {len(data)} байт, шаблон {tpl_rel}, {t1.fetch.describe()}, имя {t1.name}, "
                      f"мипы: соседние уровни {min(psnr[0]) if psnr and psnr[0] else '—'}…{max(psnr[0]) if psnr and psnr[0] else '—'} дБ")
            bad += not ok
        except Exception as e:
            bad += 1
            print(f'ОШИБКА {rel}: {e}')
print(f'файлов {n}, ошибок: {bad}')
sys.exit(1 if bad else 0)
