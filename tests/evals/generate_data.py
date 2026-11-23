"""Gera dados fictícios de uma rede de cafeterias em Curitiba para avaliar a aplicação.

Uso:
    uv run python tests/evals/generate_data.py

Saída:
    tests/evals/data/      CSVs lidos pela aplicação (uma tabela por arquivo)
    tests/evals/gabarito/  resultado mensal esperado por loja (não é carregado pela app)

A geração é determinística (SEED fixa). As regras de negócio estão em tests/evals/README.md.
"""

from __future__ import annotations

import calendar
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 20240101
ROOT = Path(__file__).parent
OUT = ROOT / "data"
GAB = ROOT / "gabarito"

START = date(2024, 1, 1)  # início do período publicado
END = date(2025, 12, 31)  # fim do período publicado
SIM_START = date(2023, 11, 1)  # aquecimento: estoque inicial e lucro de dez/2023 (base da taxa de jan/2024)
SIM_END = date(2026, 1, 31)  # consumo futuro usado para dimensionar as últimas compras

rng = np.random.default_rng(SEED)


def cents(x: float) -> int:
    return int(round(x * 100))


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def months_between(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


def add_months(y: int, m: int, k: int) -> tuple[int, int]:
    idx = y * 12 + (m - 1) + k
    return idx // 12, idx % 12 + 1


def pay_date(comp: str, offset_months: int, day: int) -> date:
    """Data de pagamento: dia `day` do mês `comp + offset`; fim de semana vai para segunda."""
    y, m = map(int, comp.split("-"))
    y, m = add_months(y, m, offset_months)
    d = date(y, m, min(day, calendar.monthrange(y, m)[1]))
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def daterange(a: date, b: date):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


# --------------------------------------------------------------------------- calendário
HOLIDAYS = {
    # nacionais + Curitiba (8/set, Nossa Senhora da Luz dos Pinhais)
    date(2023, 11, 2), date(2023, 11, 15), date(2023, 12, 25),
    date(2024, 1, 1), date(2024, 2, 12), date(2024, 2, 13), date(2024, 3, 29), date(2024, 4, 21),
    date(2024, 5, 1), date(2024, 5, 30), date(2024, 9, 7), date(2024, 9, 8), date(2024, 10, 12),
    date(2024, 11, 2), date(2024, 11, 15), date(2024, 11, 20), date(2024, 12, 25),
    date(2025, 1, 1), date(2025, 3, 3), date(2025, 3, 4), date(2025, 4, 18), date(2025, 4, 21),
    date(2025, 5, 1), date(2025, 6, 19), date(2025, 9, 7), date(2025, 9, 8), date(2025, 10, 12),
    date(2025, 11, 2), date(2025, 11, 15), date(2025, 11, 20), date(2025, 12, 25),
    date(2026, 1, 1),
}
CLOSED_ALL = {date(y, 12, 25) for y in (2023, 2024, 2025)} | {date(y, 1, 1) for y in (2024, 2025, 2026)}
SHORT_DAYS = {date(y, 12, 24) for y in (2023, 2024, 2025)} | {date(y, 12, 31) for y in (2023, 2024, 2025)}
BLACK_FRIDAY = {date(2023, 11, 24), date(2024, 11, 29), date(2025, 11, 28)}
MOTHERS_DAY_WEEK = {date(2024, 5, 12) - timedelta(days=i) for i in range(7)} | {
    date(2025, 5, 11) - timedelta(days=i) for i in range(7)
}


def cold_index(d: date) -> float:
    """+1 no auge do inverno curitibano (meados de julho), −1 no auge do verão."""
    doy = d.timetuple().tm_yday
    return math.cos(2 * math.pi * (doy - 196) / 365.25)


# --------------------------------------------------------------------------- perfis
# Sazonalidade mensal (jan..dez) por perfil de loja.
SEASON = {
    "rua": [0.84, 0.92, 1.00, 1.00, 1.04, 1.10, 1.12, 1.08, 1.02, 1.00, 0.98, 0.92],
    "centro": [0.80, 0.90, 1.02, 1.02, 1.05, 1.08, 1.06, 1.06, 1.03, 1.02, 1.00, 0.94],
    "shopping": [0.92, 0.88, 0.94, 0.96, 1.04, 1.07, 1.12, 1.01, 0.96, 0.99, 1.06, 1.27],
    "universitario": [0.62, 0.74, 1.10, 1.12, 1.12, 1.08, 0.70, 1.10, 1.12, 1.12, 1.08, 0.78],
    "fds": [0.86, 0.92, 0.98, 0.99, 1.06, 1.16, 1.20, 1.10, 1.02, 0.98, 0.96, 0.96],
}
# Dia da semana (seg..dom). 0 = loja fechada.
DOW = {
    "rua": [0.94, 0.94, 0.96, 1.00, 1.06, 1.16, 0.84],
    "centro": [1.16, 1.16, 1.14, 1.14, 1.10, 0.52, 0.0],
    "shopping": [0.80, 0.80, 0.85, 0.90, 1.10, 1.36, 1.22],
    "universitario": [1.22, 1.22, 1.20, 1.16, 1.00, 0.42, 0.0],
    "fds": [0.74, 0.74, 0.80, 0.86, 1.06, 1.46, 1.46],
}
# Pesos por hora de abertura (hora -> peso)
HOURS = {
    "rua": {7: 3, 8: 7, 9: 8, 10: 7, 11: 5, 12: 5, 13: 5, 14: 6, 15: 8, 16: 8, 17: 6, 18: 3},
    "centro": {7: 7, 8: 10, 9: 9, 10: 6, 11: 5, 12: 7, 13: 7, 14: 5, 15: 6, 16: 6, 17: 5, 18: 3},
    "shopping": {10: 3, 11: 4, 12: 6, 13: 7, 14: 7, 15: 9, 16: 10, 17: 9, 18: 7, 19: 6, 20: 5, 21: 3},
    "universitario": {7: 8, 8: 10, 9: 8, 10: 9, 11: 6, 12: 7, 13: 6, 14: 5, 15: 8, 16: 6, 17: 4, 18: 4},
    "fds": {8: 3, 9: 6, 10: 8, 11: 7, 12: 5, 13: 5, 14: 6, 15: 9, 16: 10, 17: 8, 18: 4},
}
HOURS_SAT_SHORT = {8: 5, 9: 8, 10: 9, 11: 8, 12: 5}  # centro/universitário no sábado

# --------------------------------------------------------------------------- produtos
# nome: (categoria, preço 2024, preço a partir de 01/02/2025, peso base, sensibilidade ao frio)
PRODUCTS = {
    "Espresso": ("Café", 8.00, 8.50, 10, 0.10),
    "Café coado": ("Café", 9.00, 9.50, 12, 0.15),
    "Cappuccino": ("Café", 15.00, 16.00, 14, 0.20),
    "Latte": ("Café", 16.00, 17.00, 10, 0.15),
    "Mocha": ("Café", 18.00, 19.50, 5, 0.30),
    "Chá": ("Bebida quente", 10.00, 10.50, 4, 0.35),
    "Chocolate quente": ("Bebida quente", 16.00, 17.00, 5, 0.70),
    "Suco de laranja": ("Bebida fria", 14.00, 15.00, 5, -0.40),
    "Água mineral": ("Bebida fria", 5.50, 6.00, 6, -0.35),
    "Pão de queijo": ("Salgado", 10.00, 11.00, 14, 0.10),
    "Croissant": ("Salgado", 14.00, 15.00, 6, 0.00),
    "Sanduíche natural": ("Salgado", 22.00, 24.00, 5, -0.10),
    "Bolo (fatia)": ("Doce", 14.00, 15.00, 6, 0.05),
    "Cookie": ("Doce", 9.00, 10.00, 5, 0.00),
}
PRICE_CHANGE = date(2025, 2, 1)
PRODUCT_NAMES = list(PRODUCTS)
DRINKS = {p for p, v in PRODUCTS.items() if v[0] in {"Café", "Bebida quente", "Bebida fria"} and p != "Água mineral"}

# Ajustes de mix por perfil/loja (multiplicadores de peso)
MIX = {
    "premium": {"Latte": 1.4, "Croissant": 1.5, "Mocha": 1.2, "Café coado": 0.7, "Pão de queijo": 0.8},
    "centro": {"Espresso": 1.5, "Café coado": 1.3, "Sanduíche natural": 1.3, "Mocha": 0.7},
    "shopping": {"Mocha": 1.4, "Chocolate quente": 1.3, "Cookie": 1.6, "Água mineral": 1.2, "Café coado": 0.7},
    "universitario": {"Café coado": 1.6, "Pão de queijo": 1.5, "Croissant": 0.6, "Latte": 0.8, "Mocha": 0.7},
    "fds": {"Bolo (fatia)": 1.7, "Cappuccino": 1.2, "Chocolate quente": 1.2, "Espresso": 0.7},
    "padrao": {},
}

# --------------------------------------------------------------------------- insumos (compras)
# insumo: (categoria, unidade, embalagem, preço 2024, fornecedor, grupo de entrega, desperdício)
SUPPLIES = {
    "Café em grãos": ("Café", "kg", 1, 78.00, "Torrefação Serra do Mar", "secos", 0.01),
    "Leite integral": ("Laticínios", "L", 12, 4.90, "Laticínios Vale do Iguaçu", "frescos", 0.04),
    "Chocolate em pó": ("Mercearia", "kg", 1, 42.00, "Distribuidora Araucária", "secos", 0.01),
    "Chá em sachê": ("Mercearia", "un", 100, 0.55, "Distribuidora Araucária", "secos", 0.01),
    "Açúcar em sachê": ("Mercearia", "un", 1000, 0.045, "Distribuidora Araucária", "secos", 0.02),
    "Suco de laranja integral": ("Bebidas", "L", 6, 11.50, "Distribuidora Araucária", "secos", 0.03),
    "Água mineral 500ml": ("Bebidas", "un", 12, 1.40, "Distribuidora Araucária", "secos", 0.00),
    "Pão de queijo congelado": ("Padaria", "kg", 1, 29.00, "Congelados Pinheiral", "frescos", 0.03),
    "Croissant congelado": ("Padaria", "un", 20, 3.60, "Congelados Pinheiral", "frescos", 0.05),
    "Cookie": ("Padaria", "un", 24, 2.40, "Congelados Pinheiral", "frescos", 0.02),
    "Bolo inteiro (12 fatias)": ("Confeitaria", "un", 1, 58.00, "Doceria Vó Lurdes", "frescos", 0.08),
    "Sanduíche natural": ("Lanches", "un", 1, 7.80, "Natural Lanches Curitiba", "lanches", 0.06),
    "Copo descartável 300ml": ("Descartáveis", "un", 50, 0.38, "EmbalaSul Descartáveis", "descartaveis", 0.02),
    "Tampa para copo": ("Descartáveis", "un", 50, 0.16, "EmbalaSul Descartáveis", "descartaveis", 0.02),
    "Guardanapo": ("Descartáveis", "un", 1000, 0.012, "EmbalaSul Descartáveis", "descartaveis", 0.00),
}
# consumo de insumo por unidade vendida
RECIPES = {
    "Espresso": {"Café em grãos": 0.009, "Açúcar em sachê": 0.7},
    "Café coado": {"Café em grãos": 0.015, "Açúcar em sachê": 0.7},
    "Cappuccino": {"Café em grãos": 0.009, "Leite integral": 0.15, "Chocolate em pó": 0.005, "Açúcar em sachê": 0.5},
    "Latte": {"Café em grãos": 0.009, "Leite integral": 0.22, "Açúcar em sachê": 0.4},
    "Mocha": {"Café em grãos": 0.009, "Leite integral": 0.18, "Chocolate em pó": 0.02},
    "Chá": {"Chá em sachê": 1, "Açúcar em sachê": 0.5},
    "Chocolate quente": {"Leite integral": 0.25, "Chocolate em pó": 0.03},
    "Suco de laranja": {"Suco de laranja integral": 0.3},
    "Água mineral": {"Água mineral 500ml": 1},
    "Pão de queijo": {"Pão de queijo congelado": 0.1},
    "Croissant": {"Croissant congelado": 1},
    "Sanduíche natural": {"Sanduíche natural": 1},
    "Bolo (fatia)": {"Bolo inteiro (12 fatias)": 1 / 12},
    "Cookie": {"Cookie": 1},
}
# dias de entrega por grupo (0 = segunda)
DELIVERY = {"frescos": (0, 3), "lanches": (0, 2, 4), "secos": None, "descartaveis": None}


def supply_price(item: str, d: date) -> float:
    base = SUPPLIES[item][3]
    t = months_between(date(2024, 1, 1), d)  # meses desde jan/2024 (negativo no aquecimento)
    if item == "Café em grãos":
        # alta forte do café arábica em 2024-2025
        return base * (1 + 0.019 * max(t, 0))
    price = base * (1.0055 ** max(t, 0))  # ~6,8% a.a.
    if item == "Leite integral" and d.month in (6, 7, 8, 9):
        price *= {6: 1.06, 7: 1.12, 8: 1.12, 9: 1.05}[d.month]  # entressafra do leite
    return price


# --------------------------------------------------------------------------- lojas
@dataclass
class Store:
    id: int
    nome: str
    bairro: str
    endereco: str
    tipo_local: str
    perfil: str  # chave de SEASON/DOW/HOURS
    mix: str
    abertura: date
    pct_franquia: float
    base_pedidos: float
    n_atendentes: int
    aluguel: float
    condominio: float  # só shopping
    energia: float
    agua: float
    area_m2: int
    para_viagem: float
    secos_dia: int  # dia da semana da entrega de secos
    closed: list[tuple[date, date]] = field(default_factory=list)
    season_jitter: list[float] = field(default_factory=list)


STORES = [
    Store(1, "Café Araucária Batel", "Batel", "Av. do Batel, 1450", "Rua", "rua", "premium",
          date(2021, 5, 3), 0.10, 36, 2, 3900, 0, 640, 140, 72, 0.30, 1),
    Store(2, "Café Araucária Centro", "Centro", "Rua XV de Novembro, 820", "Rua", "centro", "centro",
          date(2020, 9, 14), 0.08, 36, 2, 3300, 0, 560, 130, 58, 0.55, 2),
    Store(3, "Café Araucária Shopping Mueller", "Centro Cívico", "Shopping Mueller, piso L2", "Shopping",
          "shopping", "shopping", date(2022, 3, 7), 0.12, 33, 2, 3300, 1100, 480, 60, 34, 0.40, 1),
    Store(4, "Café Araucária ParkShopping Barigüi", "Mossunguê", "ParkShoppingBarigüi, piso térreo",
          "Shopping", "shopping", "shopping", date(2022, 11, 21), 0.15, 36, 2, 4200, 1350, 560, 70, 40, 0.40, 3),
    Store(5, "Café Araucária Água Verde", "Água Verde", "Av. República Argentina, 2210", "Rua", "rua",
          "padrao", date(2023, 2, 6), 0.07, 27, 1, 2300, 0, 430, 110, 50, 0.30, 2,
          closed=[(date(2025, 3, 10), date(2025, 3, 19))]),
    Store(6, "Café Araucária Rebouças", "Rebouças", "Av. Sete de Setembro, 3100", "Rua", "universitario",
          "universitario", date(2023, 6, 12), 0.05, 28, 1, 2100, 0, 410, 100, 45, 0.50, 3),
    Store(7, "Café Araucária Juvevê", "Juvevê", "Rua Augusto Stresser, 640", "Rua", "rua", "padrao",
          date(2024, 3, 11), 0.09, 23, 1, 2000, 0, 390, 95, 42, 0.30, 1),
    Store(8, "Café Araucária Shopping Estação", "Rebouças", "Shopping Estação, piso 1", "Shopping",
          "shopping", "shopping", date(2024, 8, 1), 0.11, 29, 1, 2900, 950, 450, 55, 30, 0.40, 2),
    Store(9, "Café Araucária Santa Felicidade", "Santa Felicidade", "Av. Manoel Ribas, 5600", "Rua", "fds",
          "fds", date(2025, 2, 3), 0.06, 21, 1, 1700, 0, 360, 90, 40, 0.20, 3),
    Store(10, "Café Araucária Ecoville", "Mossunguê", "Rua Prof. Pedro Viriato Parigot de Souza, 2900",
          "Rua", "fds", "fds", date(2025, 6, 16), 0.13, 24, 1, 2400, 0, 400, 100, 48, 0.25, 1),
]
for s in STORES:
    s.season_jitter = list(1 + rng.normal(0, 0.025, 12))  # diferenças sutis entre lojas de mesmo perfil

# --------------------------------------------------------------------------- funcionários
FIRST = ["Ana", "Beatriz", "Bruno", "Camila", "Carlos", "Daniel", "Eduarda", "Felipe", "Fernanda", "Gabriel",
         "Giovana", "Gustavo", "Helena", "Igor", "Isabela", "João", "Juliana", "Larissa", "Leonardo", "Letícia",
         "Lucas", "Luiza", "Marcelo", "Mariana", "Mateus", "Natália", "Paulo", "Rafael", "Renata", "Rodrigo",
         "Sabrina", "Thiago", "Vanessa", "Vinícius", "Yasmin", "André", "Cláudia", "Diego", "Elisa", "Otávio"]
LAST = ["Andrade", "Bittencourt", "Cardoso", "Carvalho", "Costa", "Dalla Costa", "Ferreira", "Gomes",
        "Kowalski", "Lima", "Machado", "Martins", "Mendes", "Moraes", "Nowak", "Oliveira", "Pereira", "Ribeiro",
        "Rocha", "Santos", "Schmidt", "Silva", "Souza", "Tanaka", "Wiśniewski", "Zanetti"]

BASE_SALARY = {"Gerente": 2700.0, "Atendente": 1700.0}
DISSIDIO = {date(2024, 5, 1): 1.055, date(2025, 5, 1): 1.050}  # data-base maio
BENEFICIO_MES = {2023: 480.0, 2024: 480.0, 2025: 520.0}  # VT + VR por funcionário/mês


@dataclass
class Employee:
    id: int
    nome: str
    loja: int
    cargo: str
    admissao: date
    desligamento: date | None
    salario_admissao: float

    def active(self, d: date) -> bool:
        return self.admissao <= d and (self.desligamento is None or d <= self.desligamento)

    def salary_on(self, d: date) -> float:
        s = self.salario_admissao
        for when, factor in DISSIDIO.items():
            if self.admissao < when <= d:
                s *= factor
        return round(s, 2)


def role_base(cargo: str, d: date) -> float:
    s = BASE_SALARY[cargo]
    for when, factor in DISSIDIO.items():
        if when <= d:
            s *= factor
    return s


def build_employees() -> list[Employee]:
    names = [f"{f} {l}" for f in FIRST for l in LAST]
    order = rng.permutation(len(names))
    pool = iter(names[i] for i in order)
    emps: list[Employee] = []
    for s in STORES:
        slots = [("Gerente", 1600)] + [("Atendente", 520)] * s.n_atendentes
        for cargo, mean_tenure in slots:
            if s.abertura < SIM_START:
                start = s.abertura + timedelta(days=int(rng.integers(0, max(1, (SIM_START - s.abertura).days - 30))))
                if cargo == "Gerente":
                    start = s.abertura
            else:
                start = s.abertura
            while start <= SIM_END:
                tenure = int(rng.exponential(mean_tenure)) + 90
                end = start + timedelta(days=tenure)
                # garante que ninguém esteja desligado antes do início da simulação
                if end < SIM_START:
                    start = end + timedelta(days=int(rng.integers(3, 12)))
                    continue
                desl = end if end <= END else None
                if start < date(2024, 1, 1):
                    sal0 = BASE_SALARY[cargo] + 10 * int(rng.integers(0, 16))
                else:
                    sal0 = round(role_base(cargo, start) / 10) * 10 + 10 * int(rng.integers(0, 8))
                emps.append(Employee(0, next(pool), s.id, cargo, start, desl, sal0))
                if desl is None:
                    break
                gap = 1 if cargo == "Gerente" else int(rng.integers(3, 12))
                start = desl + timedelta(days=gap)
    emps.sort(key=lambda e: (e.admissao, e.loja))
    for i, e in enumerate(emps, 1):
        e.id = i
    return emps


# --------------------------------------------------------------------------- simulação de vendas
def demand(s: Store, d: date) -> float:
    if d < s.abertura or d in CLOSED_ALL or any(a <= d <= b for a, b in s.closed):
        return 0.0
    dow = DOW[s.perfil][d.weekday()]
    if dow == 0:
        return 0.0
    holiday = 1.0
    if d in HOLIDAYS:
        if s.perfil in ("centro", "universitario"):
            return 0.0
        holiday = 1.12 if s.tipo_local == "Shopping" else 0.72
    if d in SHORT_DAYS:
        holiday *= 0.55
    if d in BLACK_FRIDAY and s.tipo_local == "Shopping":
        holiday *= 1.45
    if d in MOTHERS_DAY_WEEK and s.tipo_local == "Shopping":
        holiday *= 1.12
    days_open = (d - s.abertura).days
    ramp = 1 - 0.42 * math.exp(-days_open / 80)
    growth = 1 + 0.035 * ((d - date(2024, 1, 1)).days / 365)
    season = SEASON[s.perfil][d.month - 1] * s.season_jitter[d.month - 1]
    return s.base_pedidos * dow * holiday * ramp * growth * season


def product_weights(s: Store, d: date) -> np.ndarray:
    cold = cold_index(d)
    w = []
    for p in PRODUCT_NAMES:
        _, _, _, base, sens = PRODUCTS[p]
        w.append(base * (1 + sens * cold) * MIX[s.mix].get(p, 1.0))
    w = np.array(w)
    return w / w.sum()


def price(p: str, d: date) -> float:
    return PRODUCTS[p][2] if d >= PRICE_CHANGE else PRODUCTS[p][1]


def payment_probs(s: Store, d: date) -> list[float]:
    t = max(0, (d - date(2024, 1, 1)).days) / 730
    pix = 0.34 + 0.09 * t + (0.08 if s.perfil == "universitario" else 0) - (0.04 if s.tipo_local == "Shopping" else 0)
    credito = 0.31 + (0.06 if s.tipo_local == "Shopping" else 0) + (0.04 if s.mix == "premium" else 0)
    dinheiro = max(0.02, 0.08 - 0.03 * t + (0.03 if s.perfil in ("centro", "universitario") else 0))
    debito = 1 - pix - credito - dinheiro
    return [pix, credito, debito, dinheiro]


PAYMENTS = ["Pix", "Cartão de crédito", "Cartão de débito", "Dinheiro"]
CARD_FEE = {"Cartão de crédito": 0.031, "Cartão de débito": 0.015, "Pix": 0.0, "Dinheiro": 0.0}
SIMPLES = 0.06
FUNDO_PROMOCAO = 0.02


def simulate_sales(employees: list[Employee]):
    orders = []  # (store, datetime, emp_id, payment, total_cents)
    items = []  # (order_idx, produto, qtd, preco_cents)
    consumption: dict[tuple[int, date], dict[str, float]] = {}
    by_store = {s.id: [e for e in employees if e.loja == s.id] for s in STORES}
    for s in STORES:
        p_items = [0.44, 0.36, 0.14, 0.06] if s.mix not in ("premium", "fds") else [0.36, 0.38, 0.18, 0.08]
        for d in daterange(SIM_START, SIM_END):
            lam = demand(s, d)
            n = int(rng.poisson(lam * float(np.exp(rng.normal(0, 0.10))))) if lam > 0 else 0
            cons: dict[str, float] = {}
            if n:
                hours = HOURS_SAT_SHORT if (d.weekday() == 5 and s.perfil in ("centro", "universitario")) else HOURS[s.perfil]
                hs = np.array(list(hours))
                hw = np.array(list(hours.values()), dtype=float)
                if d in SHORT_DAYS:
                    keep = hs < (14 if s.tipo_local == "Rua" else 18)
                    hs, hw = hs[keep], hw[keep]
                hw /= hw.sum()
                pw = product_weights(s, d)
                staff = [e for e in by_store[s.id] if e.active(d)]
                sw = np.array([0.35 if e.cargo == "Gerente" else 1.0 for e in staff])
                sw /= sw.sum()
                pay = payment_probs(s, d)
                for _ in range(n):
                    h = int(rng.choice(hs, p=hw))
                    ts = datetime(d.year, d.month, d.day, h, int(rng.integers(0, 60)), int(rng.integers(0, 60)))
                    k = int(rng.choice([1, 2, 3, 4], p=p_items))
                    prods = rng.choice(len(PRODUCT_NAMES), size=k, replace=False, p=pw)
                    emp = staff[int(rng.choice(len(staff), p=sw))]
                    pm = PAYMENTS[int(rng.choice(4, p=pay))]
                    total = 0
                    viagem = rng.random() < s.para_viagem
                    oi = len(orders)
                    for pi in prods:
                        prod = PRODUCT_NAMES[pi]
                        q = 1 if rng.random() < 0.87 else int(rng.choice([2, 3], p=[0.85, 0.15]))
                        pc = cents(price(prod, d))
                        total += q * pc
                        items.append((oi, prod, q, pc))
                        for ins, per in RECIPES[prod].items():
                            cons[ins] = cons.get(ins, 0) + per * q
                        if viagem and prod in DRINKS:
                            cons["Copo descartável 300ml"] = cons.get("Copo descartável 300ml", 0) + q
                            cons["Tampa para copo"] = cons.get("Tampa para copo", 0) + q
                    cons["Guardanapo"] = cons.get("Guardanapo", 0) + 2
                    orders.append((s.id, ts, emp.id, pm, total))
            consumption[(s.id, d)] = cons
    return orders, items, consumption


# --------------------------------------------------------------------------- compras
def simulate_purchases(consumption):
    rows = []  # (store, date, fornecedor, item, categoria, unidade, qtd, preco_unit_cents)
    for s in STORES:
        start = max(SIM_START, s.abertura)
        group_days = {
            "frescos": DELIVERY["frescos"],
            "lanches": DELIVERY["lanches"],
            "secos": (s.secos_dia,),
        }
        order_dates: dict[str, list[date]] = {g: [] for g in ("frescos", "lanches", "secos", "descartaveis")}
        for d in daterange(start, SIM_END):
            for g, days in group_days.items():
                if d.weekday() in days or d == start:
                    order_dates[g].append(d)
            # descartáveis a cada 14 dias a partir da abertura/início
            if (d - start).days % 14 == 0:
                order_dates["descartaveis"].append(d)
        stock = {ins: 0.0 for ins in SUPPLIES}
        events: dict[date, list[str]] = {}
        for g, ds in order_dates.items():
            ds = sorted(set(ds))
            order_dates[g] = ds
            for d in ds:
                events.setdefault(d, []).append(g)
        group_of = {ins: v[5] for ins, v in SUPPLIES.items()}
        next_order: dict[tuple[str, date], date] = {}
        for g, ds in order_dates.items():
            for a, b in zip(ds, ds[1:] + [SIM_END + timedelta(days=1)]):
                next_order[(g, a)] = b
        for d in daterange(start, SIM_END):
            for g in events.get(d, []):
                nxt = next_order[(g, d)]
                for ins, meta in SUPPLIES.items():
                    if group_of[ins] != g:
                        continue
                    waste = meta[6]
                    need = sum(
                        consumption.get((s.id, x), {}).get(ins, 0.0) for x in daterange(d, nxt - timedelta(days=1))
                    ) * (1 + waste)
                    target = need * 1.10  # estoque de segurança
                    missing = target - stock[ins]
                    if missing <= 0:
                        continue
                    pack = meta[2]
                    qty = math.ceil(missing / pack - 1e-9) * pack
                    stock[ins] += qty
                    rows.append((s.id, d, meta[4], ins, meta[0], meta[1], qty, supply_price(ins, d)))
            for ins, q in consumption.get((s.id, d), {}).items():
                stock[ins] -= q * (1 + SUPPLIES[ins][6])
            assert all(v >= -1e-6 for v in stock.values()), (s.id, d, stock)
    return rows


# --------------------------------------------------------------------------- custos
def month_iter(a: date, b: date):
    y, m = a.year, a.month
    while (y, m) <= (b.year, b.month):
        yield y, m
        y, m = add_months(y, m, 1)


def build_costs(employees, sales_month, card_month, purchases_month):
    """Retorna linhas de custo (sem id) e o resultado mensal por loja."""
    rows = []
    result = []
    emp_by_store = {s.id: [e for e in employees if e.loja == s.id] for s in STORES}
    for s in STORES:
        first = max(SIM_START, s.abertura)
        lucro_prev = None
        for y, m in month_iter(first, END):
            comp = f"{y:04d}-{m:02d}"
            mstart, mend = date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])
            dim = calendar.monthrange(y, m)[1]
            receita = sales_month.get((s.id, comp), 0)
            mrows = []

            def add(cat, desc, valor_cents, pagto, emp_id=None):
                mrows.append((s.id, comp, pagto, cat, desc, emp_id, int(valor_cents)))

            # pessoal
            folha = 0
            benef = 0.0
            for e in emp_by_store[s.id]:
                a = max(e.admissao, mstart)
                b = min(e.desligamento or mend, mend)
                if a > b:
                    continue
                days = (b - a).days + 1
                sal = e.salary_on(mend if e.desligamento is None or e.desligamento > mend else e.desligamento)
                valor = sal if days == dim else sal * min(days, 30) / 30
                v = cents(valor)
                folha += v
                add("Salários", f"Salário - {e.nome}", v, pay_date(comp, 1, 5), e.id)
                benef += BENEFICIO_MES[y] * (1 if days == dim else min(days, 30) / 30)
            # 13º e férias provisionados mês a mês (regime de competência), sobre os salários do mês
            prov13 = round(folha / 12)
            provferias = round(folha * (4 / 3) / 12)
            add("Encargos trabalhistas", "Provisão de 13º salário (1/12 da folha)", prov13, pay_date(comp, 0, 28))
            add("Encargos trabalhistas", "Provisão de férias + 1/3 (1/12 da folha)", provferias, pay_date(comp, 0, 28))
            add("Encargos trabalhistas", "FGTS (8% sobre salários e provisões)",
                round((folha + prov13 + provferias) * 0.08), pay_date(comp, 1, 7))
            add("Benefícios", "Vale-transporte e vale-refeição", cents(benef), pay_date(comp, 0, 1))

            # ocupação
            anos = 0
            for yy in range(2024, y + 1):
                aniversario = date(yy, s.abertura.month, 1)
                if aniversario > s.abertura.replace(day=1) and aniversario <= mstart and aniversario >= date(2024, 1, 1):
                    anos += 1
            aluguel = s.aluguel * (1.045 ** anos)
            add("Aluguel", "Aluguel do ponto" + (f" (reajuste anual IPCA, {anos}x)" if anos else ""),
                cents(aluguel), pay_date(comp, 0, 10))
            if s.tipo_local == "Shopping":
                add("Taxa de shopping", "Condomínio do shopping", cents(s.condominio * (1.05 if y >= 2025 else 1)),
                    pay_date(comp, 0, 10))
                add("Taxa de shopping", "Fundo de promoção (2% do faturamento)", round(receita * FUNDO_PROMOCAO),
                    pay_date(comp, 1, 10))

            # utilidades
            act = receita / max(1, cents(s.base_pedidos * 26 * 30))
            cold = {1: -1, 2: -0.8, 3: -0.4, 4: 0.1, 5: 0.6, 6: 1, 7: 1, 8: 0.9, 9: 0.4, 10: 0, 11: -0.4, 12: -0.8}[m]
            clima = 1 + 0.16 * max(cold, 0) + (0.10 * max(-cold, 0) if s.tipo_local == "Shopping" else 0.03 * max(-cold, 0))
            tarifa = 1.0 if y == 2023 or y == 2024 else 1.065
            open_frac = 1.0 if s.abertura <= mstart else ((mend - s.abertura).days + 1) / dim
            energia = s.energia * clima * tarifa * (0.80 + 0.20 * min(act, 1.4)) * float(rng.normal(1, 0.035))
            energia = energia * (0.35 + 0.65 * open_frac)
            add("Energia elétrica", "Conta de luz (Copel)", cents(energia), pay_date(comp, 1, 15))
            agua = s.agua * (1.0 if y < 2025 else 1.055) * (0.75 + 0.25 * min(act, 1.4)) * float(rng.normal(1, 0.05))
            agua = agua * (0.35 + 0.65 * open_frac)
            add("Água", "Conta de água e esgoto (Sanepar)", cents(agua), pay_date(comp, 1, 18))
            add("Internet e telefone", "Plano de internet fibra + telefone", cents(129.90 if y < 2025 else 139.90),
                pay_date(comp, 1, 12))
            add("Sistemas", "Sistema de PDV e gestão", cents(149.00), pay_date(comp, 0, 5))
            add("Contabilidade", "Honorários contábeis", cents(380.0 if y < 2025 else 410.0), pay_date(comp, 1, 10))
            limpeza = (95 + 0.0032 * receita / 100) * float(rng.normal(1, 0.08))
            add("Material de limpeza", "Produtos de limpeza e higiene", cents(limpeza), pay_date(comp, 0, 20))

            # vendas
            add("Taxas de cartão", "Taxas de cartão (crédito 3,1% / débito 1,5%)", card_month.get((s.id, comp), 0),
                mend)
            add("Impostos", "Simples Nacional (6% do faturamento)", round(receita * SIMPLES), pay_date(comp, 1, 20))

            # eventuais
            if s.id == 5 and comp == "2025-03":
                add("Manutenção", "Reforma do salão (loja fechada de 10 a 19/03)", cents(6850.00), date(2025, 3, 21))
            elif rng.random() < 0.22:
                add("Manutenção", str(rng.choice(["Manutenção da máquina de espresso", "Conserto de refrigerador",
                                                  "Manutenção do moedor", "Reparos elétricos"])),
                    cents(float(rng.uniform(180, 950))), pay_date(comp, 0, 25))
            if comp in ("2024-11", "2025-11") or (s.abertura.year == y and s.abertura.month == m and s.abertura >= START):
                desc = "Campanha de inauguração" if s.abertura.year == y and s.abertura.month == m else "Campanha de fim de ano"
                add("Marketing", desc, cents(float(rng.uniform(350, 900))), pay_date(comp, 0, 15))

            # franquia
            meses_operacao = months_between(s.abertura, mstart)
            if lucro_prev is None:  # 1º mês simulado (aquecimento, não publicado)
                fee = round(max(0, receita - purchases_month.get((s.id, comp), 0) - sum(r[-1] for r in mrows))
                            * s.pct_franquia)
                fee_desc = "Taxa de franquia (aquecimento)"
            elif meses_operacao < 3:
                fee = 0
                fee_desc = f"Taxa de franquia isenta ({meses_operacao + 1}º mês de operação)"
            else:
                base = max(0, lucro_prev)
                fee = round(base * s.pct_franquia)
                prev = month_key(date(*add_months(y, m, -1), 1))
                base_txt = f"{lucro_prev / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                fee_desc = (f"Taxa de franquia {s.pct_franquia:.0%} sobre o lucro de {prev} (R$ {base_txt})"
                            if lucro_prev > 0 else f"Taxa de franquia {s.pct_franquia:.0%} - sem cobrança: prejuízo em {prev} (R$ {base_txt})")
            add("Taxa de franquia", fee_desc, fee, pay_date(comp, 0, 10))

            compras = purchases_month.get((s.id, comp), 0)
            custos = sum(r[-1] for r in mrows)
            lucro = receita - compras - custos
            result.append({
                "id_cafeteria": s.id, "competencia": comp, "receita_vendas": receita / 100,
                "compras": compras / 100, "custos_operacionais": custos / 100, "taxa_franquia": fee / 100,
                "lucro": lucro / 100,
            })
            lucro_prev = lucro
            rows.extend(mrows)
    return rows, result


# --------------------------------------------------------------------------- main
def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    GAB.mkdir(parents=True, exist_ok=True)
    employees = build_employees()
    orders, items, consumption = simulate_sales(employees)

    # ---- vendas / itens (apenas período publicado; consumo fora dele só alimenta as compras)
    o = pd.DataFrame(orders, columns=["id_cafeteria", "data_venda", "id_vendedor", "forma_pagamento", "total"])
    o["_idx"] = np.arange(len(o))
    it = pd.DataFrame(items, columns=["_idx", "produto", "quantidade", "preco"])
    o["comp"] = o["data_venda"].dt.strftime("%Y-%m")
    o["card"] = o["total"] * o["forma_pagamento"].map(CARD_FEE)
    sales_month = o.groupby(["id_cafeteria", "comp"])["total"].sum().to_dict()
    card_month = {k: round(v) for k, v in o.groupby(["id_cafeteria", "comp"])["card"].sum().to_dict().items()}

    in_period = (o["data_venda"] >= pd.Timestamp(START)) & (o["data_venda"] < pd.Timestamp(END + timedelta(days=1)))
    o = o[in_period].sort_values(["data_venda", "id_cafeteria"]).reset_index(drop=True)
    o["id_pedido"] = np.arange(100001, 100001 + len(o))
    o["qtd_itens"] = o["_idx"].map(it.groupby("_idx")["quantidade"].sum())
    emp_name = {e.id: e.nome for e in employees}
    vendas = pd.DataFrame({
        "id_pedido": o["id_pedido"],
        "id_cafeteria": o["id_cafeteria"],
        "data_venda": o["data_venda"].dt.strftime("%Y-%m-%d %H:%M:%S"),
        "id_vendedor": o["id_vendedor"],
        "vendedor": o["id_vendedor"].map(emp_name),
        "forma_pagamento": o["forma_pagamento"],
        "qtd_itens": o["qtd_itens"],
        "valor_total": o["total"] / 100,
    })
    it = it.merge(o[["_idx", "id_pedido", "data_venda"]], on="_idx").sort_values(["id_pedido", "_idx"], kind="stable")
    itens = pd.DataFrame({
        "id_item": np.arange(1, len(it) + 1),
        "id_pedido": it["id_pedido"].to_numpy(),
        "produto": it["produto"].to_numpy(),
        "categoria": it["produto"].map(lambda p: PRODUCTS[p][0]).to_numpy(),
        "quantidade": it["quantidade"].to_numpy(),
        "preco_unitario": (it["preco"] / 100).to_numpy(),
        "valor_total": (it["quantidade"] * it["preco"] / 100).round(2).to_numpy(),
    })

    # ---- compras
    prow = simulate_purchases(consumption)
    p = pd.DataFrame(prow, columns=["id_cafeteria", "data_pedido", "fornecedor", "item", "categoria", "unidade",
                                    "quantidade", "valor_unitario"])
    p["valor_unitario"] = p["valor_unitario"].round(2)
    small = p["valor_unitario"] < 0.10  # açúcar/guardanapo: preço unitário com 3 casas
    p.loc[small, "valor_unitario"] = [round(supply_price(i, d), 3) for i, d in zip(p.loc[small, "item"], p.loc[small, "data_pedido"])]
    p["valor_cents"] = (p["quantidade"] * p["valor_unitario"] * 100).round().astype(int)
    p["comp"] = p["data_pedido"].map(month_key)
    purchases_month = p.groupby(["id_cafeteria", "comp"])["valor_cents"].sum().to_dict()
    p = p[(p["data_pedido"] >= START) & (p["data_pedido"] <= END)].copy()
    p = p.sort_values(["data_pedido", "id_cafeteria", "fornecedor", "item"]).reset_index(drop=True)
    keys = p[["data_pedido", "id_cafeteria", "fornecedor"]].drop_duplicates().reset_index(drop=True)
    keys["id_compra"] = np.arange(5001, 5001 + len(keys))
    p = p.merge(keys, on=["data_pedido", "id_cafeteria", "fornecedor"])
    compras = pd.DataFrame({
        "id_linha": np.arange(1, len(p) + 1),
        "id_compra": p["id_compra"],
        "id_cafeteria": p["id_cafeteria"],
        "data_pedido": p["data_pedido"].map(lambda d: d.isoformat()),
        "fornecedor": p["fornecedor"],
        "item": p["item"],
        "categoria": p["categoria"],
        "unidade": p["unidade"],
        "quantidade": p["quantidade"].astype(int),
        "valor_unitario": p["valor_unitario"],
        "valor_total": p["valor_cents"] / 100,
    })

    # ---- custos
    crow, result = build_costs(employees, sales_month, card_month, purchases_month)
    c = pd.DataFrame(crow, columns=["id_cafeteria", "competencia", "data_pagamento", "categoria", "descricao",
                                    "id_funcionario", "valor"])
    c = c[c["competencia"] >= month_key(START)].reset_index(drop=True)
    c.insert(0, "id_custo", np.arange(1, len(c) + 1))
    c["data_pagamento"] = c["data_pagamento"].map(lambda d: d.isoformat())
    c["id_funcionario"] = c["id_funcionario"].astype("Int64")
    c["valor"] = c["valor"] / 100

    # ---- dimensões
    cafeterias = pd.DataFrame([{
        "id_cafeteria": s.id, "nome": s.nome, "bairro": s.bairro, "endereco": s.endereco,
        "cidade": "Curitiba", "uf": "PR", "tipo_local": s.tipo_local, "data_abertura": s.abertura.isoformat(),
        "percentual_franquia": s.pct_franquia, "area_m2": s.area_m2,
        "funciona_domingo": "Não" if DOW[s.perfil][6] == 0 else "Sim",
    } for s in STORES])
    funcionarios = pd.DataFrame([{
        "id_funcionario": e.id, "nome": e.nome, "id_cafeteria": e.loja, "cargo": e.cargo,
        "data_admissao": e.admissao.isoformat(),
        "data_desligamento": e.desligamento.isoformat() if e.desligamento else None,
        "salario_atual": e.salary_on(min(e.desligamento or END, END)),
    } for e in employees if e.admissao <= END and (e.desligamento is None or e.desligamento >= START)])

    gab = pd.DataFrame(result)
    gab = gab[gab["competencia"] >= month_key(START)]
    gab_dec = pd.DataFrame(result)
    gab_dec = gab_dec[gab_dec["competencia"] == "2023-12"][["id_cafeteria", "lucro"]].rename(
        columns={"lucro": "lucro_2023_12"})
    pedidos = vendas.assign(competencia=vendas["data_venda"].str[:7]).groupby(["id_cafeteria", "competencia"]).size()
    gab = gab.merge(pedidos.rename("qtd_pedidos").reset_index(), on=["id_cafeteria", "competencia"], how="left")
    gab["qtd_pedidos"] = gab["qtd_pedidos"].fillna(0).astype(int)
    gab = gab[["id_cafeteria", "competencia", "qtd_pedidos", "receita_vendas", "compras", "custos_operacionais",
               "taxa_franquia", "lucro"]]

    for name, df in {"cafeterias": cafeterias, "funcionarios": funcionarios, "vendas": vendas,
                     "itens_venda": itens, "compras": compras, "custos": c}.items():
        df.to_csv(OUT / f"{name}.csv", index=False, float_format="%.2f" if name != "compras" else None)
    gab.to_csv(GAB / "resultado_mensal.csv", index=False, float_format="%.2f")
    gab_dec.to_csv(GAB / "lucro_2023_12.csv", index=False, float_format="%.2f")
    for name in ("cafeterias", "funcionarios", "vendas", "itens_venda", "compras", "custos"):
        print(f"{name:14s} {sum(1 for _ in open(OUT / f'{name}.csv')) - 1:>8d} linhas")


if __name__ == "__main__":
    main()
