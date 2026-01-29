import pygame as pg
import sys, os, random, time
from typing import List, Tuple, Optional

# ---------------- フォント解決 ----------------
def get_jp_font(size: int) -> pg.font.Font:
    bundle = os.path.join("assets", "fonts", "NotoSansJP-Regular.ttf")
    if os.path.exists(bundle):
        return pg.font.Font(bundle, size)
    candidates = [
        "Noto Sans CJK JP", "Noto Sans JP",
        "Yu Gothic UI", "Yu Gothic",
        "Meiryo", "MS Gothic",
        "Hiragino Sans", "Hiragino Kaku Gothic ProN",
    ]
    for name in candidates:
        path = pg.font.match_font(name)
        if path:
            return pg.font.Font(path, size)
    return pg.font.SysFont(None, size)

# ---------------- 可変パラメータ ----------------
FRAME_DELAY = 0.2
ENEMY_DELAY = 1.0
WIN_W, WIN_H = 980, 720
FIELD_Y = 520
SLOT_W = 65
SLOT_PAD = 3
LEFT_MARGIN = 30
GEM_IMG_SIZE = (SLOT_W - 4, SLOT_W - 4) #宝石の画像サイズ

# ドラッグ演出
DRAG_SCALE = 1.18
DRAG_SHADOW = (0, 0, 0, 90)

# ---------------- 定義 ----------------
ELEMENT_SYMBOLS = {"火": "火", "水": "水", "風": "風", "土": "土", "命": "命", "無": " "}
COLOR_RGB = {
    "火": (230, 70, 70), "水": (70, 150, 230), "風": (90, 200, 120),
    "土": (200, 150, 80), "命": (220, 90, 200), "無": (160,160,160)
}
GEMS = ["火", "水", "風", "土", "命"]
SLOTS = [chr(ord('A')+i) for i in range(14)]

# ---------------- 画像 ----------------
def load_gem_image(elem: str) -> pg.Surface: #宝石の画像をロードする関数
    m = {
        "火":"fire.png", "水":"water.png",
        "風":"wind.png", "土":"earth.png",
        "命":"life.png", "無":"void.png"
    }
    fn = m.get(elem)
    if fn:
        path = os.path.join("assets","gems",fn)
        if os.path.exists(path):
            img = pg.image.load(path).convert_alpha()
            return pg.transform.smoothscale(img, GEM_IMG_SIZE)
    surf = pg.Surface(GEM_IMG_SIZE, pg.SRCALPHA); surf.fill((60,60,60,200))
    return surf

def load_monster_image(name: str) -> pg.Surface:
    m = {
        "スライム":"slime.png", "ゴブリン":"goblin.png",
        "オオコウモリ":"bat.png", "ウェアウルフ":"werewolf.png",
        "ドラゴン":"dragon.png"
    }
    fn = m.get(name)
    if fn:
        path = os.path.join("assets","monsters",fn)
        if os.path.exists(path):
            img = pg.image.load(path).convert_alpha()
            return pg.transform.smoothscale(img, (256,256))
    surf = pg.Surface((256,256), pg.SRCALPHA); surf.fill((60,60,60,200))
    return surf

# ---------------- HPバー ----------------
def hp_bar_surf(current: int, max_hp: int, w: int, h: int) -> pg.Surface:
    """HPバー（max600基準でスケーリング）"""
    # HP比（0〜1）
    ratio = max(0, min(1, current / max_hp if max_hp > 0 else 0))
    # 600を基準にスケール（例：max_hp=100なら1/6）
    scale = min(1.0, max_hp / 600.0)
    bar_w = int(w * scale)

    # HP割合で塗り幅を決定
    fill_w = int(bar_w * ratio)

    # 色（体力残量による）
    if ratio >= 0.6:
        col = (40, 200, 90)
    elif ratio >= 0.3:
        col = (230, 200, 60)
    else:
        col = (230, 70, 70)

    # バー描画
    surf = pg.Surface((w, h), pg.SRCALPHA)
    # 背景（透明）
    bg = pg.Surface((bar_w, h), pg.SRCALPHA)
    bg.fill((0, 0, 0, 120))
    surf.blit(bg, (0, 0))
    # 緑バー
    fg = pg.Surface((fill_w, h), pg.SRCALPHA)
    fg.fill(col)
    surf.blit(fg, (0, 0))
    return surf

# ---------------- 盤面ロジック ----------------
def init_field()->List[str]:
    return [random.choice(GEMS) for _ in range(14)]

def leftmost_run(field:List[str])->Optional[Tuple[int,int]]:
    n=len(field); i=0
    while i<n:
        j=i+1
        while j<n and field[j]==field[i]: j+=1
        L=j-i
        if L>=3 and field[i] in GEMS: return (i,L)
        i=j
    return None

def collapse_left(field:List[str], start:int, length:int):
    # 消滅部分を '無' にしてから左詰め（簡略：一気に詰める）
    n=len(field)
    for k in range(start, start+length): field[k]="無"
    rest=[e for e in field if e!="無"]; field[:] = rest + ["無"]*length

def fill_random(field:List[str]):
    for i,e in enumerate(field):
        if e=="無": field[i]=random.choice(GEMS)

# ---------------- ダメージ/回復 ----------------
def jitter(v:float, r:float=0.10)->int:
    return max(1, int(v*random.uniform(1-r,1+r)))

def attr_coeff(att,defe):
    cyc={"火":"風","風":"土","土":"水","水":"火"}
    if att in cyc and cyc[att]==defe: return 2.0
    if defe in cyc and cyc[defe]==att: return 0.5
    return 1.0

def party_attack_from_gems(elem:str, run_len:int, combo:int, party:dict, monster:dict)->int:
    combo_coeff = 1.5 ** ((run_len - 3) + combo)
    if elem=="命":
        heal=jitter(20*combo_coeff); party["hp"]=min(party["max_hp"], party["hp"]+heal); return 0
    ally = next((a for a in party["allies"] if a["element"]==elem), None)
    if not ally: return 0
    base=max(1, ally["ap"]-monster["dp"])
    dmg=jitter(base*attr_coeff(elem,monster["element"])*combo_coeff)
    monster["hp"]=max(0,monster["hp"]-dmg); return dmg

def enemy_attack(party:dict, monster:dict)->int:
    base=max(1, monster["ap"]-party["dp"])
    dmg=jitter(base); party["hp"]=max(0,party["hp"]-dmg); return dmg

# ---------------- 描画ユーティリティ ----------------
def slot_rect(i: int) -> pg.Rect:
    tx = LEFT_MARGIN + i * (SLOT_W + SLOT_PAD)
    return pg.Rect(tx, FIELD_Y, SLOT_W, SLOT_W)

def draw_gem_at(screen, elem: str, x: int, y: int, scale=1.0, with_shadow=False, gem_images=None):
    img = gem_images.get(elem)
    if img is None:
        return
    iw, ih = img.get_size()
    sw, sh = int(iw * scale), int(ih * scale)
    img_scl = pg.transform.smoothscale(img, (sw, sh))
    rect = img_scl.get_rect(center=(x, y))
    if with_shadow:
        shadow = pg.Surface((sw + 10, sh + 10), pg.SRCALPHA)
        pg.draw.ellipse(shadow, DRAG_SHADOW, shadow.get_rect())
        screen.blit(shadow, (rect.x - 5, rect.y - 5 + 4))
    screen.blit(img_scl, rect.topleft)

def draw_field(screen, field:List[str], font, hover_idx:Optional[int]=None,
               drag_src:Optional[int]=None, drag_elem:Optional[str]=None, gem_images=None):
    # スロット見出し
    for i,elem in enumerate(field):
        rect = slot_rect(i)
        s=font.render(SLOTS[i], True, (220,220,220))
        screen.blit(s,(rect.x + rect.width // 2 - s.get_width() // 2, rect.y - s.get_height() - 4))
    # スロット下地 & ホバー強調
    for i,_ in enumerate(field):
        rect=slot_rect(i)
        base = (35,35,40) if hover_idx!=i else (60,60,80)
        pg.draw.rect(screen, base, rect, border_radius=8)
    # 宝石（ドラッグ開始スロットは空に見せる）
    for i,elem in enumerate(field):
        if drag_src is not None and i==drag_src:
            continue
        rect=slot_rect(i)
        cx,cy=rect.center
        draw_gem_at(screen, elem, cx, cy, gem_images=gem_images)
        sym = ELEMENT_SYMBOLS[elem]
        
    # ドラッグ中の宝石（ゴースト）をカーソル位置に拡大表示
    if drag_elem is not None:
        mx, my = pg.mouse.get_pos()
        draw_gem_at(screen, drag_elem, mx, my-4, scale=DRAG_SCALE, with_shadow=True, gem_images=gem_images)

def draw_top(screen, enemy, party, font):
    # 敵画像/名前
    img = load_monster_image(enemy["name"])
    screen.blit(img, (40, 40))

    # 敵名とHPバー
    name = font.render(enemy["name"], True, (240, 240, 240))
    screen.blit(name, (320, 40))
    enemy_bar = hp_bar_surf(enemy['hp'], enemy['max_hp'], 420, 18)
    screen.blit(enemy_bar, (320, 80))

    # 敵HP数値（バー右側に）
    enemy_hp_text = font.render(f"{enemy['hp']}/{enemy['max_hp']}", True, (240, 240, 240))
    screen.blit(enemy_hp_text, (750, 78))

    # 「パーティ」ラベル
    label = font.render("パーティ", True, (240, 240, 240))
    screen.blit(label, (320, 110))

    # パーティHPバー
    party_bar = hp_bar_surf(party['hp'], party['max_hp'], 420, 18)
    screen.blit(party_bar, (320, 140))

    # パーティHP数値
    party_hp_text = font.render(f"{int(party['hp'])}/{party['max_hp']}", True, (240, 240, 240))
    screen.blit(party_hp_text, (750, 138))

def draw_message(screen, text, font):
    surf = font.render(text, True, (230,230,230))
    screen.blit(surf,(40,460))

# ---------------- タイトル画面 ----------------

def title_screen(screen: pg.Surface, font: pg.font.Font) -> bool:

#　ボタンはクリックのみ　True: ゲーム開始 / False: 終了

    title_font = get_jp_font(56)
    sub_font = get_jp_font(24)
    clock = pg.time.Clock()

    # ボタン　（追加可能）
    btn_w, btn_h = 320, 64
    start_btn = pg.Rect(WIN_W//2 - btn_w//2, 300, btn_w, btn_h)
    quit_btn  = pg.Rect(WIN_W//2 - btn_w//2, 380, btn_w, btn_h)
    #                   横　　　　　　縦　　　　　　ボタン幅　高さ
    while True:
        mx, my = pg.mouse.get_pos()#マウスの座標

        for e in pg.event.get():
            if e.type == pg.QUIT:
                return False
            if e.type == pg.KEYDOWN:
                if e.key == pg.K_ESCAPE:
                    return False
            if e.type == pg.MOUSEBUTTONDOWN and e.button == 1:
                if start_btn.collidepoint(e.pos):
                    return True
                if quit_btn.collidepoint(e.pos):
                    return False

        screen.fill((12, 12, 18))

        t = title_font.render("Puzzle & Monsters", True, (240, 240, 240))#タイトル
        screen.blit(t, (WIN_W//2 - t.get_width()//2, 170))


        # ボタン描画（ホバー機能）
        start_hover = start_btn.collidepoint(mx, my)
        quit_hover = quit_btn.collidepoint(mx, my)

        pg.draw.rect(screen, (70, 120, 220) if start_hover else (50, 90, 170), start_btn, border_radius=12)
        pg.draw.rect(screen, (220, 90, 90) if quit_hover else (170, 60, 60), quit_btn, border_radius=12)
        pg.draw.rect(screen, (230, 230, 230), start_btn, width=2, border_radius=12)
        pg.draw.rect(screen, (230, 230, 230), quit_btn, width=2, border_radius=12)
        #ボタン文字
        s1 = sub_font.render("スタート", True, (245, 245, 245))
        screen.blit(s1, (start_btn.centerx - s1.get_width()//2, start_btn.centery - s1.get_height()//2))

        s2 = sub_font.render("終了", True, (245, 245, 245))
        screen.blit(s2, (quit_btn.centerx - s2.get_width()//2, quit_btn.centery - s2.get_height()//2))

        pg.display.flip()
        clock.tick(60)

# ---------------- メイン ----------------
def main():
    pg.init()
    screen = pg.display.set_mode((WIN_W, WIN_H))
    gem_images = {elem: load_gem_image(elem) for elem in GEMS + ["無"]}
    pg.display.set_caption("Puzzle & Monsters - GUI Prototype")
    font = get_jp_font(26)

    if not title_screen(screen, font):
        pg.quit()
        sys.exit()
    back_btn = pg.Rect(WIN_W - 160, 10, 150, 38) #タイトルへ戻るボタン
    
    party = {
        "player_name":"Player",
        "allies":[
            {"name":"青龍","element":"風","hp":150,"max_hp":150,"ap":15,"dp":10},
            {"name":"朱雀","element":"火","hp":150,"max_hp":150,"ap":25,"dp":10},
            {"name":"白虎","element":"土","hp":150,"max_hp":150,"ap":20,"dp":5},
            {"name":"玄武","element":"水","hp":150,"max_hp":150,"ap":20,"dp":15},
        ],
        "hp":600, "max_hp":600, "dp":(10+10+5+15)/4
    }
    enemies = [
        {"name":"スライム","element":"水","hp":100,"max_hp":100,"ap":10,"dp":1},
        {"name":"ゴブリン","element":"土","hp":200,"max_hp":200,"ap":20,"dp":5},
        {"name":"オオコウモリ","element":"風","hp":300,"max_hp":300,"ap":30,"dp":10},
        {"name":"ウェアウルフ","element":"風","hp":400,"max_hp":400,"ap":40,"dp":15},
        {"name":"ドラゴン","element":"火","hp":600,"max_hp":600,"ap":50,"dp":20},
    ]
    enemy_idx=0
    enemy = enemies[enemy_idx]
    field = init_field()

    drag_src: Optional[int] = None
    drag_elem: Optional[str] = None
    hover_idx: Optional[int] = None
    message = "ドラッグで宝石を移動"

    clock = pg.time.Clock()
    running=True
    while running:
        for e in pg.event.get():
            if e.type==pg.QUIT:
                running=False

            elif e.type==pg.MOUSEBUTTONDOWN and e.button==1:
                # タイトルへ戻る
                if back_btn.collidepoint(e.pos):
                    if not title_screen(screen, font):
                        pg.quit()
                        sys.exit()
                    # ゲーム状態を初期化
                    party['hp'] = party['max_hp']
                    enemy_idx = 0
                    enemy = enemies[enemy_idx]
                    enemy['hp'] = enemy['max_hp']
                    field = init_field()
                    message = "ドラッグで宝石を移動"
                    drag_src = None
                    drag_elem = None
                    hover_idx = None
                    continue
                    
                mx,my = e.pos
                if FIELD_Y<=my<=FIELD_Y+SLOT_W:
                    i = (mx-LEFT_MARGIN)//(SLOT_W+SLOT_PAD)
                    if 0<=i<14:
                        drag_src = i
                        drag_elem = field[i]
                        message=f"{SLOTS[i]} を掴んだ"

            elif e.type==pg.MOUSEMOTION:
                mx,my = e.pos
                hi = (mx-LEFT_MARGIN)//(SLOT_W+SLOT_PAD)
                if 0<=hi<14 and FIELD_Y<=my<=FIELD_Y+SLOT_W:
                    hover_idx = hi
                    if drag_src is not None and hover_idx != drag_src:
                        field[drag_src], field[hover_idx] = field[hover_idx], field[drag_src]
                        drag_src = hover_idx
                else:
                    hover_idx = None

            elif e.type==pg.MOUSEBUTTONUP and e.button==1:
                if drag_src is not None:
                    combo=0
                    while True:
                            run = leftmost_run(field)
                            if not run: break
                            start,L = run
                            combo+=1
                            elem = field[start]
                            if elem=="命":
                                heal=jitter(20*(1.5**((L-3)+combo)))
                                party['hp']=min(party['max_hp'], party['hp']+heal)
                                message=f"HP +{heal}"
                            else:
                                dmg=party_attack_from_gems(elem,L,combo,party,enemy)
                                message=f"{elem}攻撃！ {dmg} ダメージ"
                            collapse_left(field,start,L)
                            screen.fill((22,22,28)); draw_top(screen, enemy, party, font)
                            draw_field(screen, field, font, gem_images=gem_images); draw_message(screen, "消滅！", font)
                            pg.display.flip(); time.sleep(FRAME_DELAY)
                            fill_random(field)
                            screen.fill((22,22,28)); draw_top(screen, enemy, party, font)
                            draw_field(screen, field, font, gem_images=gem_images); draw_message(screen, "湧き！", font)
                            pg.display.flip(); time.sleep(FRAME_DELAY)
                            if enemy['hp']<=0:
                                message=f"{enemy['name']} を倒した！"
                                break

                        # 敵ターン or 撃破後処理
                    if enemy['hp']>0:
                            edmg=enemy_attack(party, enemy)
                            message=f"{enemy['name']}の攻撃！ -{edmg}"
                            screen.fill((22,22,28)); draw_top(screen, enemy, party, font)
                            draw_field(screen, field, font, gem_images=gem_images); draw_message(screen, message, font)
                            pg.display.flip(); time.sleep(FRAME_DELAY)
                            if party['hp']<=0:
                                message="パーティは力尽きた…（ESCで終了）"
                    else:
                            enemy_idx+=1
                            if enemy_idx<len(enemies):
                                enemy=enemies[enemy_idx]
                                field=init_field()
                                message=f"さらに奥へ… 次は {enemy['name']}"
                            else:
                                message="ダンジョン制覇！おめでとう！（ESCで終了）"

                # ドラッグ終了
                drag_src = None
                drag_elem = None
                hover_idx = None

        # 常時描画
        screen.fill((22,22,28))
        draw_top(screen, enemy, party, font)
        draw_field(screen, field, font, hover_idx, drag_src, drag_elem, gem_images=gem_images)
        draw_message(screen, message, font)
        pg.display.flip()
        clock.tick(60)

         # 「タイトルへ」描画
        mx,my = pg.mouse.get_cursorget_pos(mx, my)
        back_hover = back_btn.collidepoint(mx, my)
        pg.draw.rect(screen, (80, 80, 110) if back_hover else (55, 55, 75), back_btn, border_radious=10)
        pg.draw.rest(screen, (230, 230, 230), back_btn, width=2, border_radius=10)
        btxt = get_jp_font(18).render("タイトルへ", True, (245, 245, 245))
        screen.blit(btxt, (back_btn.centerx - btxt.get_width()//2, back_btn.centery - btxt.get_height()//2))

        keys=pg.key.get_pressed()
        if keys[pg.K_ESCAPE]:
            running=False

    pg.quit()
    sys.exit()

if __name__=="__main__":
    main()









