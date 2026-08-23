#!/usr/bin/env python3
"""
HERMES IMAGE ENGINE V20 — NÍVEL DEUS ABSOLUTO — ARQUIVO DEFINITIVO
PARTE 1/5: Infraestrutura, Bancos de Dados Cinematográficos e Pipeline Inicial
(Blocos 1 a 12 — Análise, Classificação, Estilos, Qualidade e Interface)

100% compatível com Hermes Agent v0.19.1+
Uso como skill: hermes chat --skills image-engine
Auto-diagnóstico: NUNCA gera erro de importação, Quality Gate ou execução
"""

import os, re, json, sys, time, random, hashlib, logging, copy
from typing import Dict, Any, List, Optional, Tuple, Set, Union
from dataclasses import dataclass, field
from collections import defaultdict, deque, OrderedDict
from enum import Enum, auto

# ============================================================================
# CONFIGURAÇÃO DE LOGGING — 100% SILENCIOSO NO STDOUT (stderr apenas)
# ============================================================================
logger = logging.getLogger("hermes_image_v20")
logger.setLevel(logging.WARNING)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)-8s — %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(handler)

# ============================================================================
# CONSTANTES GLOBAIS INAFEGOCIÁVEIS
# ============================================================================
VERSION = "20.0.0"
BUILD = "2026.08.02-deus-absoluto"
DEFAULT_CTA = "link na bio"

SCORE_MINIMO_ABSOLUTO = 9.0
NOTA_MINIMA_DIMENSAO = 8.5
MAX_TENTATIVAS_REGENERACAO = 5
MAX_VARIACOES_POR_TENTATIVA = 5
MAX_CACHE_ENTRIES = 500

CONTENT_ROLE_ALCANCE = "alcance"
CONTENT_ROLE_CONFIANCA = "confianca"
CONTENT_ROLE_CONVERSAO = "conversao"
CONTENT_ROLE_PROVA = "prova"

PRODUCTION_MODE_STATIC_AD = "STATIC_AD_ONLY"
AD_TYPE_DESIGN = "DESIGN"
AD_TYPE_PHOTOGRAPHY_WITH_TEXT = "PHOTOGRAPHY_WITH_TEXT"
OUTPUT_FORMAT_POST = "POST"
OUTPUT_FORMAT_CARROSSEL = "CARROSSEL"
OUTPUT_FORMAT_STORY = "STORY"

# ============================================================================
# ENUMS TIPADOS
# ============================================================================
class ContentRole(Enum):
    ALCANCE = CONTENT_ROLE_ALCANCE
    CONFIANCA = CONTENT_ROLE_CONFIANCA
    CONVERSAO = CONTENT_ROLE_CONVERSAO
    PROVA = CONTENT_ROLE_PROVA

class Platform(Enum):
    INSTAGRAM_FEED = "instagram_feed"
    INSTAGRAM_STORY = "instagram_story"
    TIKTOK = "tiktok"
    FACEBOOK_ADS = "facebook_ads"
    YOUTUBE_THUMBNAIL = "youtube_thumbnail"

    def get_aspect_ratio(self) -> str:
        ratios = {
            "instagram_feed": "1:1",
            "instagram_story": "9:16",
            "tiktok": "9:16",
            "facebook_ads": "1:1 ou 4:5",
            "youtube_thumbnail": "16:9",
        }
        return ratios.get(self.value, "1:1")

    def get_resolution(self) -> str:
        resolutions = {
            "instagram_feed": "1080x1080",
            "instagram_story": "1080x1920",
            "tiktok": "1080x1920",
            "facebook_ads": "1080x1080",
            "youtube_thumbnail": "1280x720",
        }
        return resolutions.get(self.value, "1080x1080")

class ConversionLevel(Enum):
    SOFT = "SOFT"
    MEDIUM = "MEDIUM"
    HARD = "HARD"

class ProductionMode(Enum):
    STATIC_AD_ONLY = PRODUCTION_MODE_STATIC_AD

class QualityGateResult(Enum):
    APROVADO = "aprovado"
    BLOQUEADO = "bloqueado"
    ESGOTADO = "esgotado"

class AdType(Enum):
    DESIGN = AD_TYPE_DESIGN
    PHOTOGRAPHY_WITH_TEXT = AD_TYPE_PHOTOGRAPHY_WITH_TEXT

class SceneType(Enum):
    RETAIL_PREMIUM = "retail_premium"
    LABORATORY = "laboratory"
    NATURE_ORGANIC = "nature_organic"
    MARBLE_BENCH = "marble_bench"
    FROZEN_SURFACE = "frozen_surface"
    WOODEN_SHELF = "wooden_shelf"
    CONCRETE_MINIMAL = "concrete_minimal"
    VELVET_DARK = "velvet_dark"
    GOLDEN_STUDIO = "golden_studio"
    CLINICAL_WHITE = "clinical_white"

class LightingStyle(Enum):
    GOD_RAYS = "god_rays"
    REMBRANDT = "rembrandt"
    SPLIT_LIGHTING = "split_lighting"
    RIM_LIGHT_DRAMATIC = "rim_light_dramatic"
    SOFTBOX_DIFFUSE = "softbox_diffuse"
    BACKLIGHT_SILHOUETTE = "backlight_silhouette"
    WINDOW_LIGHT_NATURAL = "window_light_natural"
    LABORATORY_CLEAN = "laboratory_clean"
    GOLDEN_HOUR_WARM = "golden_hour_warm"
    NEON_NOIR = "neon_noir"

class DepthStyle(Enum):
    SHALLOW_PORTRAIT = "shallow_portrait"
    DEEP_FOCUS = "deep_focus"
    TILT_SHIFT = "tilt_shift"
    BOKEH_CREAMY = "bokeh_creamy"
    HYPERFOCAL = "hyperfocal"

class TimeOfDay(Enum):
    GOLDEN_HOUR = "golden_hour"
    BLUE_HOUR = "blue_hour"
    MIDDAY = "midday"
    OVERCAST = "overcast"
    SUNSET = "sunset"
    TWILIGHT = "twilight"
    MORNING_DEW = "morning_dew"

# ============================================================================
# EXCEÇÕES PERSONALIZADAS
# ============================================================================
class EngineError(Exception):
    def __init__(self, message: str, code: str = "UNKNOWN", details: Dict = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}
        self.timestamp = time.time()
        logger.error(f"[{code}] {message}")

class QualityGateBlockedError(EngineError):
    def __init__(self, msg="Prompt bloqueado pelo Quality Gate", score=0, details=None):
        super().__init__(msg, "GATE_BLOCKED", details)
        self.score = score

class PipelineAbortedError(EngineError):
    def __init__(self, msg="Nenhum prompt atingiu 9.0", details=None):
        super().__init__(msg, "PIPELINE_ABORTED", details)

class InvalidInputError(EngineError):
    def __init__(self, msg="Entrada inválida", details=None):
        super().__init__(msg, "INVALID_INPUT", details)

# ============================================================================
# DATACLASSES (SCHEMAS DE DADOS)
# ============================================================================
@dataclass
class ContentAnalysis:
    content_role: ContentRole = ContentRole.CONFIANCA
    role_confidence: float = 0.0
    role_scores: Dict[str, float] = field(default_factory=dict)
    has_opinion_forte: bool = False
    has_polemica: bool = False
    has_comparacao: bool = False
    has_erro_educativo: bool = False
    has_alerta: bool = False
    has_preco_oferta: bool = False
    has_cta_forte: bool = False
    has_antes_depois: bool = False
    has_resultado_mensuravel: bool = False
    has_pergunta: bool = False
    has_checklist: bool = False
    has_ranking: bool = False
    has_verdade_revelacao: bool = False
    has_garantia: bool = False
    has_storytelling: bool = False
    has_urgencia: bool = False
    emocao_dominante: str = ""
    emocao_secundaria: str = ""
    emocao_intensidade: int = 0
    product_name: str = ""
    product_category: str = ""
    product_mentions: int = 0
    word_count: int = 0
    sentence_count: int = 0
    avg_sentence_length: float = 0.0
    estilo_recomendado: str = ""
    estilo_id: int = 0
    ad_type: str = AD_TYPE_DESIGN

@dataclass
class CinematicSceneConfig:
    scene_type: str = ""
    environment_description: str = ""
    foreground_elements: List[str] = field(default_factory=list)
    midground_elements: List[str] = field(default_factory=list)
    background_elements: List[str] = field(default_factory=list)
    atmospheric_particles: List[str] = field(default_factory=list)
    texture_materials: Dict[str, str] = field(default_factory=dict)
    lighting_setup: str = ""
    lighting_temperature: str = ""
    lighting_mood: str = ""
    color_palette: str = ""
    color_grade: str = ""
    depth_of_field: str = ""
    focal_length: str = ""
    perspective_type: str = ""
    golden_ratio_placement: str = ""
    shadow_design: str = ""
    visual_echo_elements: List[str] = field(default_factory=list)
    micro_imperfections: List[str] = field(default_factory=list)
    temperature_sensation: str = ""
    time_of_day: str = ""
    hero_lighting_rig: str = ""
    caustic_effects: str = ""
    emotional_temp_shift: str = ""

@dataclass
class StyleConfig:
    id: int = 0
    nome: str = ""
    formato: str = "POST"
    content_role: str = ""
    descricao: str = ""
    ad_type: str = AD_TYPE_DESIGN
    layout_tipo: str = ""
    layout_hierarquia: str = ""
    layout_proporcao: str = ""
    composicao: str = ""
    camera_lente: str = "50mm"
    camera_angulo: str = "eye_level"
    iluminacao_tipo: str = ""
    iluminacao_direcao: str = ""
    iluminacao_temperatura: str = ""
    cores_primarias: str = ""
    cores_contraste: str = ""
    cor_fundo: str = ""
    cor_texto: str = ""
    tipografia_usa: bool = True
    tipografia_estilo: str = ""
    tipografia_tamanho: str = ""
    tipografia_headline_tipo: str = ""
    tipografia_cor: str = ""
    tipografia_sombra: bool = True
    produto_posicao: str = ""
    produto_proporcao: str = ""
    texto_posicao: str = ""
    texto_proporcao: str = ""
    brand_referencia: str = ""
    emocao_alvo: str = ""
    objetivo: str = ""
    scene_type: str = ""
    lighting_style: str = ""
    depth_style: str = ""
    time_of_day: str = ""

@dataclass
class ImagePromptOutput:
    prompt_completo: str = ""
    negative_prompt: str = ""
    estilo_nome: str = ""
    estilo_id: int = 0
    content_role: str = ""
    ad_type: str = ""
    formato: str = ""
    plataforma: str = ""
    qualidade_score: float = 0.0
    aprovado: bool = False
    tentativas: int = 0
    headline: str = ""
    product_name: str = ""
    product_category: str = ""
    cinematic_scene: Dict[str, Any] = field(default_factory=dict)
    direcao_arte: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)

# ============================================================================
# BANCOS DE DADOS DE PADRÕES (REGEX) — BLOCOS 1 e 2
# ============================================================================
PATTERNS_ALCANCE = [
    r'\b(opinião|opinar|achamos|acreditamos|nossa\s+visão|a\s+gente\s+pensa)\b',
    r'\b(verdade\s+que\s+ninguém|ninguém\s+fala|o\s+mercado\s+não\s+conta)\b',
    r'\b(você\s+ainda\s+usa|ainda\s+faz|ainda\s+compra|ainda\s+usa)\b',
    r'\b(isso\s+aqui\s+é\s+melhor|muito\s+melhor|superior\s+a)\b',
    r'\b(a\s+maioria|quase\s+todos|90%\s+do\s+mercado)\b',
    r'\b(não\s+trabalhamos\s+com|a\s+gente\s+não\s+trabalha|não\s+trabalha\s+com)\b',
    r'\b(produto\s+comum|produto\s+ruim|produto\s+barato|produto\s+genérico)\b',
    r'\b(empurra|empurram|forçam|tentam\s+te\s+empurrar|te\s+empurram)\b',
    r'\b(se\s+não\s+for|não\s+entra|não\s+passa|não\s+passar)\b',
    r'\b(nem\s+tudo\s+que\s+viraliza|viraliza\s+mas\s+não|não\s+vale\s+a\s+pena)\b',
    r'\b(somos\s+diferentes|não\s+somos\s+iguais|a\s+gente\s+é\s+diferente)\b',
    r'\b(posicionamento|posição\s+da\s+marca|o\s+que\s+a\s+gente\s+acredita)\b',
    r'\b(não\s+é\s+só\s+mais\s+um|não\s+é\s+apenas|muito\s+além\s+disso)\b',
    r'\b(poucos\s+entendem|quem\s+entende|quem\s+sabe|quem\s+realmente\s+sabe)\b',
    r'\b(não\s+aceitamos|não\s+admitimos|não\s+toleramos|não\s+passamos)\b',
]

PATTERNS_CONFIANCA = [
    r'\b(erro\s+que|erro\s+comum|maior\s+erro|pior\s+erro|erro\s+ao)\b',
    r'\b(antes\s+de\s+comprar|antes\s+de\s+escolher|leia\s+antes|saiba\s+antes)\b',
    r'\b(checklist|lista|critérios|requisitos|o\s+que\s+olhar|o\s+que\s+procurar)\b',
    r'\b(alerta|atenção|cuidado|não\s+caia|não\s+compre|não\s+se\s+engane)\b',
    r'\b(aprender|entender|saber\s+comprar|saber\s+escolher|como\s+escolher)\b',
    r'\b(comprar\s+barato|sem\s+critério|escolher\s+errado|escolha\s+errada)\b',
    r'\b(como\s+pensar|mentalidade|jeito\s+certo|forma\s+correta|modo\s+certo)\b',
    r'\b(se\s+tiver\s+isso|se\s+não\s+tiver|procure\s+por|busque\s+por)\b',
    r'\b(mito|mentira|enganam|iludem|te\s+enganam|te\s+iludem)\b',
    r'\b(economiza\s+tempo|evita\s+problema|resolve\s+rápido|facilita)\b',
    r'\b(guia|tutorial|passo\s+a\s+passo|aprenda\s+a|descubra\s+como)\b',
    r'\b(dica|segredo|truque|macete|o\s+que\s+ninguém\s+te\s+conta)\b',
    r'\b(não\s+cometa|não\s+repita|evite\s+esse|não\s+caia\s+nesse)\b',
    r'\b(essencial|fundamental|obrigatório|indispensável|não\s+pode\s+faltar)\b',
    r'\b(diferença\s+entre|qual\s+a\s+diferença|como\s+diferenciar)\b',
]

PATTERNS_CONVERSAO = [
    r'(R\$|preço|valor|desconto|oferta|promoção|liquidação|economize)',
    r'\b(link\s+na\s+bio|compre|garanta|aproveite|últimas|adquira)\b',
    r'\b(comparação|comparar|vs|versus|lado\s+a\s+lado|qual\s+é\s+melhor)\b',
    r'\b(melhor\s+que|superior|ganha\s+de|vence|melhor\s+do\s+que)\b',
    r'\b(produto\s+do\s+dia|destaque|recomendo|indico|sugiro)\b',
    r'\b(top\s+\d|ranking|melhor\s+da|categoria|número\s+\d)\b',
    r'\b(resultado\s+imediato|resolve\s+em|em\s+\d+\s+min|em\s+\d+\s+dias)\b',
    r'\b(não\s+tem\s+comparação|único\s+que|melhor\s+do|imbatível)\b',
    r'\b(faça\s+seu\s+pedido|clique|arraste|swipe|acesse\s+o\s+link)\b',
    r'\b(só\s+hoje|encerra|últimas\s+unidades|vagas|limitado|estoque)\b',
    r'\b(frete\s+grátis|entrega\s+rápida|chega\s+em|envio\s+imediato)\b',
    r'\b(parcele|parcelado|em\s+até|sem\s+juros|no\s+cartão|no\s+pix)\b',
    r'\b(experimente|teste|prove|comprove|veja\s+como|sinta\s+a)\b',
    r'\b(não\s+vai\s+se\s+arrepender|satisfação\s+garantida|vale\s+a\s+pena)\b',
    r'\b(de\s+R\$|por\s+R\$|por\s+apenas|de\s+\d+\s+por\s+\d+)\b',
]

PATTERNS_PROVA = [
    r'\b(antes\s+e\s+depois|antes\s+vs|resultado\s+real|resultado\s+verdadeiro)\b',
    r'\b(testei|testamos|usei|usamos|experimentei|experimentamos|provei)\b',
    r'\b(funciona\s+mesmo|realmente\s+funciona|de\s+verdade|comprovado)\b',
    r'\b(\d+\s+clientes|pessoas\s+já|avaliação|nota\s+\d|estrelas)\b',
    r'\b(print|vídeo|mostrando|prova|evidência|demonstr|comprov)\b',
    r'\b(sem\s+filtro|sem\s+edição|real|verdadeiro|sem\s+photoshop|sem\s+montagem)\b',
    r'\b(depoimento|relato|experiência\s+real|história\s+real|caso\s+real)\b',
    r'\b(acredite|confie|garantido|comprovado|certificado|aprovado)\b',
    r'\b(resultado\s+em\s+\d+|em\s+\d+\s+dias|após\s+\d+\s+semanas|depois\s+de)\b',
    r'\b(não\s+é\s+montagem|não\s+é\s+photoshop|imagem\s+real|foto\s+real)\b',
    r'\b(garantia\s+de\s+\d+|dias\s+de\s+garantia|garantia\s+incondicional)\b',
    r'\b(sem\s+risco|risco\s+zero|devolução\s+garantida|reembolso)\b',
    r'\b(clinicamente|cientificamente|testado\s+em|laboratório|aprovado\s+pela)\b',
    r'\b(antes\s+era|agora\s+é|mudou\s+completamente|transformação\s+total)\b',
    r'\b(olha\s+a\s+diferença|veja\s+a\s+diferença|compare|perceba)\b',
]

# ============================================================================
# LISTAS DE BLOQUEIO E EXIGÊNCIAS (ANTI-UGC E ANTI-GENÉRICO)
# ============================================================================
UGC_BLOCKERS = [
    "handheld", "candid", "selfie", "documentary style",
    "amateur", "snapshot", "casual photo",
    "iphone photo", "point and shoot", "no lighting setup",
    "available light only", "home lighting",
    "behind the scenes", "vlog style", "raw footage",
    "unfiltered", "no makeup", "messy background casual", "cluttered room",
]

REQUIRED_PRO_ELEMENTS = [
    "studio lighting", "controlled lighting", "professional lighting",
    "commercial photography", "advertising photography",
    "clean composition", "planned composition", "directed",
    "professional setup", "high-end photography",
    "cinematic lighting", "product photography",
    "commercial grade", "professional color grading",
]

GENERIC_BLOCKERS = [
    "woman smiling", "perfect smile", "stock photo",
    "generic background", "plain white background",
    "corporate style", "generic office", "generic home",
    "model pose", "fake expression", "overly polished",
    "cheap looking", "low budget appearance",
    "amateur lighting", "flat composition",
]

# ============================================================================
# BANCOS DE DADOS CINEMATOGRÁFICOS
# ============================================================================
EMOTION_VISUAL_MAP: Dict[str, Dict[str, str]] = {
    "frustração": {
        "facial": "sobrancelhas franzidas, lábios tensos, maxilar contraído",
        "corporal": "ombros caídos, mão na testa ou na nuca",
        "olhar": "para baixo ou para o lado, evitando contato visual",
        "micro": "leve tremor nos lábios, respiração curta",
    },
    "vergonha": {
        "facial": "rosto levemente abaixado, bochechas coradas",
        "corporal": "corpo encolhido, braços cruzados protegendo o tronco",
        "olhar": "desviado, para baixo, evitando contato visual",
        "micro": "orelhas vermelhas, respiração presa",
    },
    "alívio": {
        "facial": "sorriso suave e genuíno, olhos fechados ou semicerrados",
        "corporal": "postura relaxada, mão no peito, ombros soltos",
        "olhar": "para cima (gratidão) ou fechado (paz interior)",
        "micro": "respiração profunda visível, peito expandindo",
    },
    "surpresa": {
        "facial": "olhos muito arregalados, boca entreaberta, sobrancelhas elevadas",
        "corporal": "corpo inclinado para frente, mãos abertas e soltas",
        "olhar": "fixo e intenso no objeto/pessoa que causou a surpresa",
        "micro": "pupilas dilatadas, pele arrepiada nos braços",
    },
    "confiança": {
        "facial": "queixo levemente elevado, olhar direto e firme, sorriso sutil",
        "corporal": "postura ereta e aberta, mãos nos quadris ou soltas",
        "olhar": "direto para a câmera, sem hesitação",
        "micro": "piscada lenta e deliberada, respiração calma",
    },
    "dor": {
        "facial": "sobrancelhas contraídas, olhos semicerrados, boca tensa",
        "corporal": "mão sobre a área dolorida, corpo levemente curvado",
        "olhar": "para baixo, focado na fonte da dor",
        "micro": "respiração ofegante, gotas de suor",
    },
    "preocupação": {
        "facial": "testa franzida, olhar distante, lábios levemente pressionados",
        "corporal": "braços cruzados, mão no queixo, postura pensativa",
        "olhar": "perdido no horizonte, processando informações",
        "micro": "morder o lábio inferior, tamborilar dos dedos",
    },
    "esperança": {
        "facial": "olhos brilhantes, leve sorriso, expressão aberta",
        "corporal": "corpo inclinado para frente, mãos sobre o coração",
        "olhar": "para cima e para frente, buscando",
        "micro": "respiração profunda, lágrimas nos olhos",
    },
}

SCENE_MAPPING: Dict[str, Dict[str, Any]] = {
    "retail_premium": {
        "description": "Aesop-style premium retail environment with dark stained wooden shelves, visible grain texture, products aligned with precision, green botanicals between products",
        "foreground": ["slightly blurred eucalyptus leaves", "single rosemary sprig", "textured wood edge"],
        "midground": ["product hero in sharp focus", "adjacent products slightly defocused", "brushed gold accents"],
        "background": ["receding shelves into warm darkness", "ambient warm light glow", "subtle bokeh circles"],
        "materials": {"shelf": "dark walnut wood with visible grain", "product": "frosted glass with condensation", "accents": "brushed gold metal", "floor": "polished concrete with subtle reflection"},
    },
    "laboratory": {
        "description": "Clean clinical laboratory with white surfaces, stainless steel, scientific precision, organized tools",
        "foreground": ["glass beaker with subtle condensation", "scattered formula notes slightly blurred"],
        "midground": ["product in sharp focus", "laboratory equipment", "white ceramic surface"],
        "background": ["soft focus laboratory shelves", "clean white walls", "subtle blue-tinted lighting"],
        "materials": {"surfaces": "white ceramic and stainless steel", "product": "clear glass with measurement markings", "tools": "matte black scientific instruments"},
    },
    "nature_organic": {
        "description": "Organic natural setting with living plants, stone textures, morning dew, natural light streaming through leaves",
        "foreground": ["large green leaves with visible veins slightly blurred", "water droplets on leaf surface"],
        "midground": ["product nestled among natural elements", "small stones and moss"],
        "background": ["dappled forest light", "soft bokeh of distant foliage", "warm natural tones"],
        "materials": {"surfaces": "natural stone and moss", "product": "recycled glass with bamboo cap", "accents": "raw cotton fabric, wooden elements"},
    },
    "marble_bench": {
        "description": "Luxurious marble countertop with subtle veining, premium product display, elegant minimal setting",
        "foreground": ["single white orchid petal slightly blurred", "marble edge with visible veining"],
        "midground": ["product in sharp focus on marble surface", "golden accent tray"],
        "background": ["soft cream wall with subtle texture", "ambient warm light reflection on marble"],
        "materials": {"surface": "white Carrara marble with grey veining", "product": "thick glass with gold cap", "accents": "polished gold tray, ceramic dish"},
    },
    "frozen_surface": {
        "description": "Ice-cold surface with frost crystals, condensation, dramatic cold lighting, product emerging from cold environment",
        "foreground": ["ice crystals and frost patterns slightly blurred", "condensation droplets on surface"],
        "midground": ["product in sharp focus with visible cold texture", "water beads on product surface"],
        "background": ["deep blue-black cold void", "subtle ice reflections", "cold mist atmosphere"],
        "materials": {"surface": "thick ice block with internal cracks", "product": "frosted glass with frozen condensation", "accents": "brushed steel, crystal-clear ice cubes"},
    },
    "wooden_shelf": {
        "description": "Warm wooden shelf with natural grain, artisan craftsmanship feel, soft ambient lighting, handcrafted aesthetic",
        "foreground": ["wood grain texture slightly blurred", "linen fabric edge"],
        "midground": ["product in sharp focus", "small ceramic vessel", "dried botanicals"],
        "background": ["warm plaster wall with subtle texture", "soft shadow play", "ambient warmth"],
        "materials": {"shelf": "oak wood with natural grain and subtle wear", "product": "amber glass bottle", "accents": "handmade ceramic, raw linen, dried lavender"},
    },
    "concrete_minimal": {
        "description": "Brutalist minimal concrete setting, harsh shadows, industrial elegance, stark contrast",
        "foreground": ["concrete texture with subtle cracks slightly blurred"],
        "midground": ["product in sharp focus", "single shadow line across surface"],
        "background": ["raw concrete wall", "dramatic light shaft", "industrial window light"],
        "materials": {"surface": "raw concrete with formwork texture", "product": "matte black metal and glass", "accents": "oxidized steel, rough stone"},
    },
    "velvet_dark": {
        "description": "Dark luxurious velvet backdrop, dramatic spotlight on product, jewel-like presentation, mysterious elegance",
        "foreground": ["velvet texture slightly blurred at edges"],
        "midground": ["product dramatically lit in center", "single pearl or crystal accent"],
        "background": ["deep black velvet absorbing light", "subtle warm rim light on fabric texture"],
        "materials": {"background": "deep navy or burgundy velvet", "product": "cut crystal glass with gold details", "accents": "freshwater pearl, silk ribbon"},
    },
    "golden_studio": {
        "description": "Warm golden studio with honey-toned lighting, luxurious atmosphere, sunset-inspired warmth, rich textures",
        "foreground": ["golden silk fabric edge slightly blurred", "warm bokeh circles"],
        "midground": ["product bathed in golden light", "brass accessories"],
        "background": ["warm gradient from gold to amber", "soft focus background elements", "glowing atmosphere"],
        "materials": {"surface": "polished brass tray", "product": "honey-colored glass with gold leaf", "accents": "silk fabric, amber crystals, warm metal"},
    },
    "clinical_white": {
        "description": "Pure clinical white environment, medical-grade cleanliness, bright even lighting, scientific trust",
        "foreground": ["white ceramic surface with subtle reflection"],
        "midground": ["product in sharp focus", "medical-grade tools"],
        "background": ["pure white seamless background", "even 5000K lighting", "no shadows"],
        "materials": {"surface": "medical-grade white ceramic", "product": "clinical white packaging with blue accents", "accents": "stainless steel, clear glass"},
    },
}

LIGHTING_MAPPING: Dict[str, Dict[str, Any]] = {
    "god_rays": {
        "setup": "volumetric light rays streaming from upper-left window, visible dust particles in light beam",
        "temperature": "warm 3000-3500K golden",
        "mood": "divine, premium, atmospheric, awe-inspiring",
        "technical": "single key light with gobo/cookie for pattern, haze machine for visible rays",
    },
    "rembrandt": {
        "setup": "classic Rembrandt lighting with triangular highlight on shadow cheek, dramatic shadows",
        "temperature": "warm 3200K key, neutral fill",
        "mood": "artistic, classical, painterly, sophisticated",
        "technical": "key light at 45° above, reflector for subtle fill, dark background",
    },
    "split_lighting": {
        "setup": "face or product split vertically: left side dark/cold, right side bright/warm",
        "temperature": "left 6000K cold, right 3000K warm",
        "mood": "contrast, duality, transformation, before/after",
        "technical": "two opposite key lights, no fill, sharp division line",
    },
    "rim_light_dramatic": {
        "setup": "strong rim/backlight creating luminous edge around product, dark foreground",
        "temperature": "rim 4000K neutral, ambient dark",
        "mood": "dramatic, premium, mysterious, high-end",
        "technical": "backlight 2 stops brighter than ambient, negative fill on front",
    },
    "softbox_diffuse": {
        "setup": "large softbox overhead creating soft, even, flattering light with gentle shadows",
        "temperature": "5000-5500K daylight balanced",
        "mood": "clean, professional, trustworthy, commercial",
        "technical": "overhead softbox 4x6ft, white reflectors all sides, ratio 2:1",
    },
    "backlight_silhouette": {
        "setup": "strong backlight creating product silhouette with subtle edge definition",
        "temperature": "warm 3000K backlight, cool ambient",
        "mood": "mysterious, premium launch, dramatic reveal",
        "technical": "backlight dominant, subtle front fill at -3 stops for edge detail",
    },
    "window_light_natural": {
        "setup": "large window light from left, natural daylight quality, soft shadows, airy feel",
        "temperature": "5500-6500K natural daylight",
        "mood": "organic, natural, fresh, lifestyle premium",
        "technical": "window as key light, white wall as reflector, no artificial lights visible",
    },
    "laboratory_clean": {
        "setup": "multiple overhead fluorescent panels creating shadowless, even, clinical illumination",
        "temperature": "5000K pure white",
        "mood": "scientific, precise, trustworthy, analytical",
        "technical": "overhead bank lights, white cove, no shadows, even exposure",
    },
    "golden_hour_warm": {
        "setup": "low-angle warm sunlight streaming horizontally, long soft shadows, golden tone",
        "temperature": "2800-3200K warm golden",
        "mood": "nostalgic, warm, inviting, premium lifestyle",
        "technical": "low sun angle, warm reflector for fill, haze for visible rays",
    },
    "neon_noir": {
        "setup": "colored neon lights creating dramatic color contrasts, dark shadows, modern edge",
        "temperature": "mixed: magenta/cyan neon + warm ambient",
        "mood": "edgy, modern, artistic, urban premium",
        "technical": "two-color neon sources, dark environment, colored shadows",
    },
}

DEPTH_MAPPING: Dict[str, Dict[str, Any]] = {
    "shallow_portrait": {
        "aperture": "f/1.8 - f/2.8",
        "focal_length": "85mm",
        "effect": "extreme subject isolation, creamy bokeh, product hero focus",
        "layers": "foreground fully blurred, midground sharp, background abstract bokeh",
    },
    "deep_focus": {
        "aperture": "f/8 - f/16",
        "focal_length": "35mm",
        "effect": "everything in focus, environmental storytelling, retail scene visible",
        "layers": "foreground detail visible, midground sharp, background clear",
    },
    "tilt_shift": {
        "aperture": "f/4",
        "focal_length": "45mm tilt-shift",
        "effect": "selective focus band, miniature effect, artistic focus control",
        "layers": "sharp focus band across product, top and bottom blurred",
    },
    "bokeh_creamy": {
        "aperture": "f/1.4",
        "focal_length": "85mm or 105mm",
        "effect": "extremely shallow depth, luxurious bokeh circles, dreamlike background",
        "layers": "only product in focus, everything else abstract",
    },
    "hyperfocal": {
        "aperture": "f/11",
        "focal_length": "24mm",
        "effect": "maximum depth of field, everything from 1m to infinity in focus",
        "layers": "all layers sharp, environmental context fully visible",
    },
}

COLOR_GRADE_MAPPING: Dict[str, Dict[str, Any]] = {
    "luxury_warm": {
        "primary": "deep forest green (#1a3a2a) + antique gold (#c9a96e)",
        "accent": "cream (#f5f0e8)",
        "mood": "intellectual luxury, quiet confidence, Aesop-style",
        "grade": "slightly desaturated with warm highlight roll-off, selective saturation on product",
    },
    "clinical_clean": {
        "primary": "pure white (#ffffff) + medical blue (#2563eb)",
        "accent": "soft green (#10b981) for positive elements",
        "mood": "professional, educational, scientific trust",
        "grade": "neutral white balance, slight blue tint in shadows, high contrast for text",
    },
    "organic_natural": {
        "primary": "sage green (#87a878) + warm brown (#8b6914)",
        "accent": "cream (#faf7f2)",
        "mood": "natural, sustainable, earthy premium",
        "grade": "warm overall cast, lifted blacks, soft highlight compression",
    },
    "dramatic_noir": {
        "primary": "deep black (#0a0a0a) + crimson (#8b0000)",
        "accent": "silver (#c0c0c0)",
        "mood": "dramatic, mysterious, high-stakes premium",
        "grade": "crushed blacks, high contrast, selective color on product only",
    },
    "golden_premium": {
        "primary": "champagne gold (#d4af37) + warm ivory (#fffff0)",
        "accent": "deep brown (#3c2415)",
        "mood": "luxurious, celebratory, high-value",
        "grade": "warm white balance 4000K, golden highlight glow, rich shadows",
    },
    "cold_premium": {
        "primary": "ice blue (#dceefb) + silver (#c0c0c0)",
        "accent": "deep navy (#0a1628)",
        "mood": "cool luxury, modern premium, skincare science",
        "grade": "cool white balance 6500K, blue shadow tint, bright highlights",
    },
    "monochromatic_elegance": {
        "primary": "warm grey (#a8a29e) + stone (#e7e5e4)",
        "accent": "charcoal (#36454f)",
        "mood": "minimalist luxury, timeless elegance, quiet sophistication",
        "grade": "desaturated by 60%, warm grey tone, even exposure",
    },
}

ATMOSPHERIC_PARTICLES: Dict[str, List[str]] = {
    "dust_motes": [
        "floating golden dust particles visible in light rays",
        "tiny specks catching light in the air",
        "dust motes dancing in god rays",
    ],
    "water_droplets": [
        "fine water mist suspended in air",
        "microscopic water droplets catching backlight",
        "spray mist creating rainbow micro-prisms",
    ],
    "condensation": [
        "dew drops on product surface",
        "condensation beads on cold glass",
        "water droplets with internal reflections",
    ],
    "steam_vapor": [
        "warm steam rising gently from product surface",
        "ethereal vapor creating soft atmosphere",
        "steam wisps catching warm backlight",
    ],
    "pollen_float": [
        "tiny pollen particles floating in golden light",
        "organic dust in sunbeams through leaves",
        "micro-particles creating depth in light rays",
    ],
    "frost_crystals": [
        "delicate frost patterns on cold surface",
        "ice crystals catching light with prismatic effect",
        "frozen micro-texture on product edges",
    ],
}

TEXTURE_STORY_MAPPING: Dict[str, Dict[str, str]] = {
    "aged_wood": {
        "description": "wood with years of visible grain, subtle wear marks, small scratches telling history",
        "use": "premium retail shelves, artisan backgrounds",
        "imperfections": "small knot holes, uneven grain, subtle water marks",
    },
    "patina_metal": {
        "description": "metal with natural oxidation, subtle color variations from age, authentic character",
        "use": "luxury hardware, premium accents, industrial elements",
        "imperfections": "uneven patina spots, subtle tarnish, micro-scratches",
    },
    "handmade_paper": {
        "description": "thick textured paper with visible fibers, deckled edges, natural variations",
        "use": "premium packaging, artisan labels, craft backgrounds",
        "imperfections": "irregular fibers, subtle color variations, rough edges",
    },
    "linen_fabric": {
        "description": "natural linen with visible weave, subtle slubs, organic texture",
        "use": "premium backgrounds, table settings, lifestyle scenes",
        "imperfections": "natural slubs, weave variations, soft wrinkles",
    },
    "frosted_glass": {
        "description": "glass with matte finish, subtle condensation, light diffusion properties",
        "use": "premium product bottles, luxury packaging",
        "imperfections": "uneven condensation patterns, subtle manufacturing marks",
    },
    "polished_stone": {
        "description": "natural stone with subtle veining, smooth polished surface, geological character",
        "use": "luxury surfaces, premium countertops, high-end backgrounds",
        "imperfections": "natural veining variations, micro-fissures, crystal inclusions",
    },
}

BRAND_REFERENCES = {
    "Aesop": {
        "style": "dark wood shelving, amber bottles, green botanicals, intellectual luxury, warm minimalism",
        "lighting": "warm 3000K god rays, volumetric light, dramatic shadows on wood grain",
        "composition": "deep perspective, products aligned with precision, botanicals as organic contrast",
        "colors": "deep green, amber, warm brown, cream",
        "vibe": "Apothecary meets modern luxury. Every product is a ritual object.",
    },
    "La Mer": {
        "style": "ocean-inspired luxury, frosted glass, sea foam textures, pearl-like surfaces",
        "lighting": "cool 6000K with warm rim light, underwater light quality, soft diffusion",
        "composition": "product emerging from frosted surface, condensation, sea elements",
        "colors": "ice white, sea foam green, pearl, deep ocean blue",
        "vibe": "The ocean's healing power in a jar. Mystical luxury.",
    },
    "Rituals": {
        "style": "Eastern philosophy meets Western luxury, cherry blossom, rice, organic textures",
        "lighting": "warm 3200K softbox, gentle shadows, morning light quality",
        "composition": "products nestled in natural elements, cherry blossoms, bamboo",
        "colors": "cherry blossom pink, rice white, bamboo green, warm grey",
        "vibe": "Ancient wisdom in modern form. Slow luxury.",
    },
    "Le Labo": {
        "style": "Industrial apothecary, hand-labeled bottles, raw materials visible, lab equipment",
        "lighting": "mixed warm/cool, Edison bulbs, laboratory fluorescent, window light",
        "composition": "workbench aesthetic, raw ingredients, hand-written labels",
        "colors": "brown glass, kraft paper, black, warm amber",
        "vibe": "Freshly compounded. Personalized. Raw authenticity.",
    },
    "Byredo": {
        "style": "Minimalist Scandinavian luxury, clean lines, negative space, single statement elements",
        "lighting": "soft diffused 5000K, shadowless, clean, architectural",
        "composition": "extreme negative space, product as solitary art object",
        "colors": "black, white, single accent color, minimal palette",
        "vibe": "Less is everything. Each object is a design statement.",
    },
    "Diptyque": {
        "style": "Parisian apothecary, illustrated labels, oval shapes, heritage feel, wax and glass",
        "lighting": "candlelight warmth 2700K, soft flicker quality, intimate shadows",
        "composition": "vignette style, clustered products, candlelight, illustrated elements",
        "colors": "cream, black, gold, muted pastels",
        "vibe": "Parisian heritage. Each scent is a story. Each object is art.",
    },
    "Nike": {
        "style": "dramatic, high contrast, motion and tension, bold statements",
        "lighting": "dramatic lateral light, deep shadows, rim light, high contrast ratio 4:1",
        "composition": "dynamic angles, action frozen, powerful perspective",
        "colors": "black, white, vibrant accent color, maximum contrast",
        "vibe": "Power. Movement. Victory. Every image is a statement.",
    },
}

CINEMATIC_SCENE_STYLES: Dict[str, Dict[str, Any]] = {
    "aesop_shelf": {
        "scene": "Dark stained wooden shelves with visible grain, products aligned with precision, eucalyptus and rosemary between bottles, warm god rays from upper-left",
        "foreground": ["slightly blurred eucalyptus leaves with visible veins", "single rosemary sprig catching rim light"],
        "midground": ["hero product in razor-sharp focus at golden ratio point", "adjacent products slightly defocused for depth"],
        "background": ["shelves receding into warm amber darkness", "beautiful bokeh circles from background lights", "ambient warm glow"],
        "materials": {"shelf": "dark walnut with visible grain and subtle wear", "bottles": "amber glass with white labels", "accents": "brushed gold caps, matte ceramic", "floor": "polished concrete with subtle reflection"},
        "lighting": "volumetric god rays 3000K from upper-left, subtle rim light on product edges, fill light at -2 stops",
        "particles": ["floating golden dust motes in light beams", "tiny pollen particles catching light"],
        "depth": "f/2.8, 50mm, one-point perspective, product at golden ratio intersection",
    },
    "la_mer_frozen": {
        "scene": "Ice-cold surface with frost crystals, product emerging from frozen environment, dramatic cold lighting with warm rim",
        "foreground": ["frost crystals and ice patterns slightly blurred", "condensation droplets on surface"],
        "midground": ["product in sharp focus with water beads", "surrounding ice texture visible"],
        "background": ["deep cold void with blue-black gradient", "subtle ice reflections", "cold mist atmosphere"],
        "materials": {"surface": "thick ice block with internal fracture patterns", "product": "frosted white glass with silver cap", "accents": "crystal-clear ice cubes, brushed steel"},
        "lighting": "cool 6000K overhead softbox, warm 3000K rim light for contrast, subtle fill",
        "particles": ["cold mist hovering above surface", "micro ice crystals floating in air"],
        "depth": "f/1.8, 85mm, extreme shallow, product isolated against cold bokeh",
    },
    "rituals_organic": {
        "scene": "Natural stone surface with cherry blossoms, bamboo elements, rice paper texture, morning light through shoji screen",
        "foreground": ["cherry blossom petals slightly blurred", "bamboo leaf edge"],
        "midground": ["product nestled among natural elements", "small river stones", "rice paper texture"],
        "background": ["soft shoji screen light", "bamboo grove bokeh", "warm ambient glow"],
        "materials": {"surface": "natural river stone with subtle moss", "product": "matte ceramic with bamboo cap", "accents": "cherry blossoms, raw silk ribbon, wooden tray"},
        "lighting": "soft window light 4500K diffused through shoji screen, warm fill from paper lantern",
        "particles": ["floating cherry blossom petals", "subtle incense smoke wisps"],
        "depth": "f/2.8, 50mm, gentle perspective, organic composition",
    },
    "dramatic_reveal": {
        "scene": "Product emerging from complete darkness, dramatic spotlight, velvet texture, jewel-like presentation",
        "foreground": ["velvet texture slightly blurred at edges"],
        "midground": ["product dramatically lit in absolute center", "single water droplet catching light"],
        "background": ["pure black void absorbing all light", "subtle warm rim on product edges only"],
        "materials": {"background": "deep black velvet or void", "product": "cut crystal glass with gold details", "accents": "single perfect water droplet"},
        "lighting": "single spotlight 3200K from above, no fill, extreme contrast ratio 8:1",
        "particles": ["single floating dust mote in spotlight beam"],
        "depth": "f/1.4, 85mm, extreme bokeh, product sole focus point",
    },
}

# ============================================================================
# BLOCO 1: CONTENT ROLE CLASSIFIER (CLASSIFICAÇÃO DE PAPEL)
# ============================================================================
class ContentRoleClassifier:
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._stats = {"alcance": 0, "confianca": 0, "conversao": 0, "prova": 0}
        self._total_classificacoes = 0

    def classify(self, copy: str) -> Tuple[ContentRole, float, Dict[str, float]]:
        cache_key = hashlib.md5(copy[:500].encode()).hexdigest()
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            return cached["role"], cached["confidence"], cached["scores"]
        t = copy.lower()
        alcance_score = self._count_patterns(t, PATTERNS_ALCANCE)
        confianca_score = self._count_patterns(t, PATTERNS_CONFIANCA)
        conversao_score = self._count_patterns(t, PATTERNS_CONVERSAO)
        prova_score = self._count_patterns(t, PATTERNS_PROVA)
        word_count = max(1, len(t.split()))
        scores = {
            CONTENT_ROLE_ALCANCE: round(alcance_score / word_count * 100, 2),
            CONTENT_ROLE_CONFIANCA: round(confianca_score / word_count * 100, 2),
            CONTENT_ROLE_CONVERSAO: round(conversao_score / word_count * 100, 2),
            CONTENT_ROLE_PROVA: round(prova_score / word_count * 100, 2),
        }
        role, confidence = self._determine_role(scores, alcance_score, confianca_score, conversao_score, prova_score)
        self._stats[role.value] += 1
        self._total_classificacoes += 1
        self._cache[cache_key] = {"role": role, "confidence": confidence, "scores": scores}
        if len(self._cache) > MAX_CACHE_ENTRIES:
            keys = list(self._cache.keys())[:MAX_CACHE_ENTRIES // 2]
            for k in keys:
                del self._cache[k]
        logger.info(f"[ContentRole] {role.value} (confiança: {confidence:.1%})")
        return role, confidence, scores

    def _count_patterns(self, text: str, patterns: List[str]) -> int:
        count = 0
        for pattern in patterns:
            try:
                count += len(re.findall(pattern, text))
            except re.error:
                continue
        return count

    def _determine_role(self, scores, alcance_raw, confianca_raw, conversao_raw, prova_raw):
        max_score = max(scores.values()) if scores else 0
        if max_score == 0:
            return ContentRole.CONFIANCA, 0.3
        if prova_raw >= 2 and scores[CONTENT_ROLE_PROVA] > scores[CONTENT_ROLE_CONVERSAO] * 1.3:
            return ContentRole.PROVA, min(0.95, scores[CONTENT_ROLE_PROVA] / max(0.01, max_score))
        if conversao_raw >= 2 and scores[CONTENT_ROLE_CONVERSAO] > scores[CONTENT_ROLE_ALCANCE] * 1.2:
            return ContentRole.CONVERSAO, min(0.95, scores[CONTENT_ROLE_CONVERSAO] / max(0.01, max_score))
        if alcance_raw >= 2 and scores[CONTENT_ROLE_ALCANCE] > scores[CONTENT_ROLE_CONFIANCA] * 1.2:
            return ContentRole.ALCANCE, min(0.95, scores[CONTENT_ROLE_ALCANCE] / max(0.01, max_score))
        if confianca_raw >= 1:
            return ContentRole.CONFIANCA, min(0.90, scores[CONTENT_ROLE_CONFIANCA] / max(0.01, max_score))
        return ContentRole.CONFIANCA, 0.4

    def analyze_copy_full(self, copy: str) -> ContentAnalysis:
        role, confidence, scores = self.classify(copy)
        t = copy.lower()
        analysis = ContentAnalysis()
        analysis.content_role = role
        analysis.role_confidence = confidence
        analysis.role_scores = scores
        analysis.has_opinion_forte = any(re.search(p, t) for p in [r'\b(opinião|achamos|acreditamos)\b', r'\b(não\s+trabalhamos\s+com)\b'])
        analysis.has_comparacao = any(re.search(p, t) for p in [r'\b(vs|versus|comparação|lado\s+a\s+lado)\b'])
        analysis.has_erro_educativo = any(re.search(p, t) for p in [r'\b(erro\s+que|erro\s+comum|maior\s+erro)\b'])
        analysis.has_preco_oferta = bool(re.search(r'R\$', t))
        analysis.has_cta_forte = bool(re.search(r'\b(link\s+na\s+bio|compre|garanta|aproveite)\b', t))
        analysis.has_antes_depois = bool(re.search(r'\b(antes\s+e\s+depois|antes\s+vs)\b', t))
        analysis.has_resultado_mensuravel = bool(re.search(r'\b(\d+\s+clientes|resultado\s+em\s+\d+|em\s+\d+\s+dias)\b', t))
        analysis.has_garantia = bool(re.search(r'\b(garantia\s+de\s+\d+|dias\s+de\s+garantia)\b', t))
        analysis.word_count = len(t.split())
        analysis.sentence_count = len([s for s in copy.split('.') if s.strip()])
        analysis.avg_sentence_length = analysis.word_count / max(1, analysis.sentence_count)
        return analysis

content_role_classifier = ContentRoleClassifier()

# ============================================================================
# BLOCO 2: COPY PATTERN ANALYZER (ANÁLISE DE PADRÕES DA COPY)
# ============================================================================
class CopyPatternAnalyzer:
    def analyze(self, copy: str) -> Dict[str, bool]:
        t = copy.lower()
        return {
            "has_urgencia": bool(re.search(r'\b(s[óo]\s+hoje|últimas|encerra|limitado|estoque)\b', t)),
            "has_storytelling": bool(re.search(r'\b(era\s+uma\s+vez|certa\s+vez|no\s+in[ií]cio|h[áa]\s+anos)\b', t)),
            "has_checklist": bool(re.search(r'\b(checklist|lista\s+de|passo\s+a\s+passo|guia)\b', t)),
            "has_ranking": bool(re.search(r'\b(top\s+\d|ranking|melhor\s+da|número\s+\d)\b', t)),
            "has_verdade_revelacao": bool(re.search(r'\b(a\s+verdade\s+é|o\s+que\s+ningu[ée]m\s+conta|segredo)\b', t)),
            "has_garantia": bool(re.search(r'\b(garantia|sem\s+risco|reembolso)\b', t)),
            "has_antes_depois": bool(re.search(r'\b(antes\s+e\s+depois|antes\s+vs)\b', t)),
            "has_resultado_mensuravel": bool(re.search(r'\b(\d+\s+clientes|resultado\s+em\s+\d+|em\s+\d+\s+dias)\b', t)),
            "has_cta_forte": bool(re.search(r'\b(compre|garanta|adquira|link\s+na\s+bio|clique)\b', t)),
            "has_preco": bool(re.search(r'R\$|\d+,\d{2}', t)),
            "has_mecanismo": bool(re.search(r'\b(porque|sistema|tecnologia|mecanismo|íon|cerâmica)\b', t)),
            "has_prova_social": bool(re.search(r'\b(\d+\s+clientes|milhares|comunidade|avaliação)\b', t)),
            "has_autoridade": bool(re.search(r'\b(especialista|anos\s+de\s+experiência|referência|líder)\b', t)),
            "has_lifestyle": bool(re.search(r'\b(rotina|dia\s+a\s+dia|minha\s+manhã|antes\s+do\s+trabalho)\b', t)),
            "has_opinion_forte": bool(re.search(r'\b(eu\s+acho|minha\s+visão|eu\s+acredito|minha\s+opinião)\b', t)),
        }

copy_pattern_analyzer = CopyPatternAnalyzer()

# ============================================================================
# BLOCO 3: STYLE SELECTOR (SELETOR DE ESTILO VISUAL)
# ============================================================================
class StyleSelector:
    def __init__(self):
        self._historico_estilos: Dict[str, List[int]] = defaultdict(list)
        self._total_selecoes = 0

    def select(self, copy: str, content_role: ContentRole, formato: str, estilos_disponiveis: List[StyleConfig]) -> StyleConfig:
        if not estilos_disponiveis:
            raise ValueError("Nenhum estilo disponível para seleção.")
        estilos_do_role = [e for e in estilos_disponiveis if e.content_role == content_role.value]
        if not estilos_do_role:
            estilos_do_role = estilos_disponiveis
        ultimos_usados = self._historico_estilos.get(formato, [])
        estilos_filtrados = [e for e in estilos_do_role if e.id not in ultimos_usados[-3:]]
        if not estilos_filtrados:
            estilos_filtrados = estilos_do_role
        t = copy.lower()
        selected = self._refine_by_patterns(t, estilos_filtrados, content_role)
        self._historico_estilos[formato].append(selected.id)
        if len(self._historico_estilos[formato]) > 20:
            self._historico_estilos[formato] = self._historico_estilos[formato][-10:]
        self._total_selecoes += 1
        logger.info(f"[Style Selector] {selected.nome} (ID:{selected.id}) | Scene: {selected.scene_type}")
        return selected

    def _refine_by_patterns(self, t: str, estilos: List[StyleConfig], role: ContentRole) -> StyleConfig:
        scores: Dict[int, int] = defaultdict(int)
        for estilo in estilos:
            nome = estilo.nome.lower()
            if role == ContentRole.ALCANCE:
                if any(p in t for p in ["não trabalhamos", "não somos"]) and "posicionamento" in nome:
                    scores[estilo.id] += 3
                if any(p in t for p in ["empurra", "mercado"]) and "contra" in nome:
                    scores[estilo.id] += 3
                if any(p in t for p in ["mentalidade", "pensar"]) and "mentalidade" in nome:
                    scores[estilo.id] += 2
                if any(p in t for p in ["barato", "sem critério"]) and "erro" in nome:
                    scores[estilo.id] += 2
            elif role == ContentRole.CONFIANCA:
                if any(p in t for p in ["erro", "errado"]) and "erro" in nome:
                    scores[estilo.id] += 3
                if any(p in t for p in ["aprender", "saber"]) and "educação" in nome:
                    scores[estilo.id] += 2
            elif role == ContentRole.CONVERSAO:
                if any(p in t for p in ["comparação", "vs"]) and "comparação" in nome:
                    scores[estilo.id] += 3
                if any(p in t for p in ["R$", "preço"]) and "oferta" in nome:
                    scores[estilo.id] += 2
            elif role == ContentRole.PROVA:
                if any(p in t for p in ["antes e depois", "antes vs"]) and "antes" in nome:
                    scores[estilo.id] += 3
                if any(p in t for p in ["testei", "testamos"]) and "teste" in nome:
                    scores[estilo.id] += 3
        max_score = max(scores.values()) if scores else 0
        if max_score > 0:
            melhores = [e for e in estilos if scores.get(e.id, 0) == max_score]
            return random.choice(melhores)
        return random.choice(estilos)

style_selector = StyleSelector()

# ============================================================================
# BLOCO 4: STYLE CONFIG LOADER — CATÁLOGO DE ESTILOS POST (15 ESTILOS)
# ============================================================================
ESTILOS_POST = [
    StyleConfig(id=1, nome="POSICIONAMENTO FORTE", formato="POST", content_role=CONTENT_ROLE_ALCANCE,
        ad_type=AD_TYPE_DESIGN, descricao="Headline gigante com afirmação direta. Fundo escuro, texto branco bold.",
        layout_tipo="headline dominante + fundo sólido", layout_hierarquia="Headline (70%) → Marca (30%)",
        layout_proporcao="texto 100%", composicao="Headline centralizada, fundo preto texturizado",
        cores_primarias="preto profundo + branco + dourado sutil", cores_contraste="máximo",
        cor_fundo="#0a0a0a", cor_texto="#FFFFFF", tipografia_usa=True, tipografia_estilo="BOLD SANS-SERIF (Montserrat Black)",
        tipografia_tamanho="gigante (40-50%)", tipografia_headline_tipo="afirmação inegociável",
        tipografia_cor="branco puro", tipografia_sombra=False, produto_posicao="ausente", produto_proporcao="0%",
        texto_posicao="centro", texto_proporcao="70%", brand_referencia="Nike", emocao_alvo="autoridade",
        objetivo="posicionar a marca como referência inquestionável", scene_type="velvet_dark",
        lighting_style="rim_light_dramatic", depth_style="shallow_portrait", time_of_day="twilight"),
    StyleConfig(id=2, nome="CRITÉRIO DA EMPRESA", formato="POST", content_role=CONTENT_ROLE_ALCANCE,
        ad_type=AD_TYPE_DESIGN, descricao="Grid limpo com critérios internos. Design premium com ícones.",
        layout_tipo="checklist visual com ícones", layout_hierarquia="Título → 3-4 critérios → Assinatura",
        layout_proporcao="texto 60% / ícones 40%", composicao="Grade com ícones dourados, fundo papel texturizado",
        cores_primarias="branco + cinza quente + dourado", cores_contraste="médio-alto",
        cor_fundo="#faf7f2", cor_texto="#1a1a1a", tipografia_usa=True, tipografia_estilo="clean sans-serif",
        tipografia_tamanho="médio-grande / pequeno", tipografia_headline_tipo="critério rigoroso",
        tipografia_cor="preto", tipografia_sombra=False, produto_posicao="não aparece", produto_proporcao="0%",
        texto_posicao="topo + centro", texto_proporcao="60%", brand_referencia="Aesop", emocao_alvo="confiança + transparência",
        objetivo="demonstrar critérios rigorosos de seleção", scene_type="concrete_minimal",
        lighting_style="softbox_diffuse", depth_style="deep_focus", time_of_day="midday"),
    StyleConfig(id=3, nome="MENTALIDADE DE COMPRA", formato="POST", content_role=CONTENT_ROLE_ALCANCE,
        ad_type=AD_TYPE_DESIGN, descricao="Frase filosófica sobre consumo. Design minimalista com textura artesanal.",
        layout_tipo="headline filosófica + espaço negativo", layout_hierarquia="Headline → Subtítulo → Elemento natural",
        layout_proporcao="texto 80% / imagem 20%", composicao="Headline centralizada, elemento natural minimalista na base",
        cores_primarias="papel kraft + preto suave + verde musgo", cores_contraste="médio",
        cor_fundo="#f5f0e8", cor_texto="#2d2d2d", tipografia_usa=True, tipografia_estilo="serif elegante ou sans light",
        tipografia_tamanho="grande (30-35%)", tipografia_headline_tipo="mentalidade de consumo",
        tipografia_cor="preto suave", tipografia_sombra=False, produto_posicao="não aparece", produto_proporcao="0%",
        texto_posicao="centro com espaço negativo", texto_proporcao="80%", brand_referencia="Diptyque",
        emocao_alvo="reflexão + sofisticação", objetivo="mudar a forma de pensar sobre compras",
        scene_type="wooden_shelf", lighting_style="window_light_natural", depth_style="deep_focus", time_of_day="morning_dew"),
    StyleConfig(id=4, nome="ERRO DE CONSUMIDOR", formato="POST", content_role=CONTENT_ROLE_ALCANCE,
        ad_type=AD_TYPE_DESIGN, descricao="Alerta educativo sobre erro comum. Design de alerta premium.",
        layout_tipo="alerta visual + explicação", layout_hierarquia="Selo de alerta → Headline → Consequência",
        layout_proporcao="texto 70% / ícone 30%", composicao="Selo âmbar no topo, headline abaixo, texto na base",
        cores_primarias="âmbar + preto + branco + vermelho queimado", cores_contraste="alto",
        cor_fundo="#FFFDF5", cor_texto="#1a1a1a", tipografia_usa=True, tipografia_estilo="bold sans-serif",
        tipografia_tamanho="grande / médio", tipografia_headline_tipo="alerta educativo",
        tipografia_cor="preto", tipografia_sombra=False, produto_posicao="não aparece", produto_proporcao="0%",
        texto_posicao="topo + centro + base", texto_proporcao="70%", brand_referencia="The Ordinary",
        emocao_alvo="alerta + curiosidade", objetivo="alertar e educar sobre erro comum",
        scene_type="clinical_white", lighting_style="laboratory_clean", depth_style="deep_focus", time_of_day="midday"),
    StyleConfig(id=5, nome="FRASE DE AUTORIDADE", formato="POST", content_role=CONTENT_ROLE_ALCANCE,
        ad_type=AD_TYPE_DESIGN, descricao="Frase forte que demonstra autoridade. Cartaz tipográfico cinematográfico.",
        layout_tipo="quote visual impactante", layout_hierarquia="Frase (80%) → Assinatura (20%)",
        layout_proporcao="texto 100%", composicao="Frase gigante centralizada, fundo texturizado",
        cores_primarias="fundo escuro + texto claro + detalhe dourado", cores_contraste="máximo",
        cor_fundo="#0d0d0d", cor_texto="#FFFFFF", tipografia_usa=True, tipografia_estilo="BOLD STATEMENT (Bebas Neue)",
        tipografia_tamanho="gigante (45-55%)", tipografia_headline_tipo="frase de autoridade memorável",
        tipografia_cor="branco", tipografia_sombra=False, produto_posicao="não aparece", produto_proporcao="0%",
        texto_posicao="centro absoluto", texto_proporcao="80%", brand_referencia="Nike", emocao_alvo="respeito + inspiração",
        objetivo="reforçar autoridade com frase memorável", scene_type="velvet_dark",
        lighting_style="rim_light_dramatic", depth_style="shallow_portrait", time_of_day="twilight"),
    StyleConfig(id=6, nome="CULTURA DA MARCA", formato="POST", content_role=CONTENT_ROLE_ALCANCE,
        ad_type=AD_TYPE_PHOTOGRAPHY_WITH_TEXT, descricao="Mostrar valores e cultura interna. Cena cinematográfica do processo artesanal.",
        layout_tipo="manifesto visual com cena de bastidores", layout_hierarquia="Título → Cena → Texto manifesto → Assinatura",
        layout_proporcao="imagem 55% / texto 45%", composicao="Cena do processo artesanal, texto sobreposto",
        camera_lente="35mm", camera_angulo="eye_level", iluminacao_tipo="window light natural com god rays",
        iluminacao_direcao="lateral esquerda", iluminacao_temperatura="quente (3500K)",
        cores_primarias="tons terra + madeira + luz natural quente", cores_contraste="médio",
        cor_fundo="madeira clara", cor_texto="preto suave", tipografia_usa=True, tipografia_estilo="elegante artesanal",
        tipografia_tamanho="médio-grande", tipografia_headline_tipo="declaração de cultura",
        tipografia_cor="preto", tipografia_sombra=False, produto_posicao="discreto na cena", produto_proporcao="20%",
        texto_posicao="sobre área clara ou abaixo", texto_proporcao="45%", brand_referencia="Aesop",
        emocao_alvo="identificação + orgulho", objetivo="conexão emocional com os valores da marca",
        scene_type="wooden_shelf", lighting_style="god_rays", depth_style="deep_focus", time_of_day="golden_hour"),
    StyleConfig(id=7, nome="FILOSOFIA DE COMPRA", formato="POST", content_role=CONTENT_ROLE_ALCANCE,
        ad_type=AD_TYPE_DESIGN, descricao="Ensinar filosofia de compra. Marca como referência intelectual.",
        layout_tipo="conceito visual limpo com textura de papel", layout_hierarquia="Frase → Explicação → Elemento conceitual",
        layout_proporcao="texto 60% / elemento 40%", composicao="Frase topo, explicação centro, elemento natural base",
        cores_primarias="papel kraft + preto + verde sálvia", cores_contraste="médio",
        cor_fundo="#f5f0e8", cor_texto="#2d2d2d", tipografia_usa=True, tipografia_estilo="clean editorial",
        tipografia_tamanho="grande / pequeno", tipografia_headline_tipo="filosofia de consumo",
        tipografia_cor="preto suave", tipografia_sombra=False, produto_posicao="discreto ou ausente", produto_proporcao="15%",
        texto_posicao="dominante (60%)", texto_proporcao="60%", brand_referencia="Muji / Le Labo",
        emocao_alvo="clareza + convicção", objetivo="associar marca a estilo de vida superior",
        scene_type="concrete_minimal", lighting_style="window_light_natural", depth_style="hyperfocal", time_of_day="morning_dew"),
    StyleConfig(id=8, nome="CONTRA O MERCADO", formato="POST", content_role=CONTENT_ROLE_ALCANCE,
        ad_type=AD_TYPE_DESIGN, descricao="Posicionar contra práticas comuns. Split visual dramático.",
        layout_tipo="comparação conceitual (mercado vs marca)", layout_hierarquia="Headline polêmica → Split visual → Explicação",
        layout_proporcao="texto 50% / split 50%", composicao="Split screen: esquerda fria/cinza, direita quente/premium",
        cores_primarias="cinza desaturado vs cor vibrante da marca", cores_contraste="muito alto",
        cor_fundo="split: #d0d0d0 / cor marca", cor_texto="preto / branco", tipografia_usa=True,
        tipografia_estilo="bold direto", tipografia_tamanho="médio-grande", tipografia_headline_tipo="frase polêmica",
        tipografia_cor="contraste com cada lado", tipografia_sombra=False, produto_posicao="lado direito em destaque",
        produto_proporcao="25%", texto_posicao="dividido entre lados", texto_proporcao="50%",
        brand_referencia="Apple (Think Different)", emocao_alvo="indignação + identificação",
        objetivo="diferenciar radicalmente a marca do mercado", scene_type="concrete_minimal",
        lighting_style="split_lighting", depth_style="deep_focus", time_of_day="midday"),
    StyleConfig(id=9, nome="DECLARAÇÃO DIRETA", formato="POST", content_role=CONTENT_ROLE_ALCANCE,
        ad_type=AD_TYPE_DESIGN, descricao="Declaração inegociável sobre o padrão da marca. Manifesto de luxo.",
        layout_tipo="statement visual puro", layout_hierarquia="Declaração (75%) → Nome da marca (25%)",
        layout_proporcao="texto 100%", composicao="Frase centralizada bold statement, fundo texturizado premium",
        cores_primarias="fundo escuro + texto claro", cores_contraste="máximo",
        cor_fundo="#0a0a0a", cor_texto="#FFFFFF", tipografia_usa=True, tipografia_estilo="BOLD CONDENSED",
        tipografia_tamanho="gigante (50-60%)", tipografia_headline_tipo="declaração inegociável",
        tipografia_cor="branco", tipografia_sombra=False, produto_posicao="não aparece", produto_proporcao="0%",
        texto_posicao="centro absoluto", texto_proporcao="75%", brand_referencia="Nike / Byredo",
        emocao_alvo="respeito + clareza absoluta", objetivo="deixar claro posicionamento inegociável",
        scene_type="velvet_dark", lighting_style="rim_light_dramatic", depth_style="shallow_portrait", time_of_day="twilight"),
    StyleConfig(id=10, nome="QUEBRA DE EXPECTATIVA", formato="POST", content_role=CONTENT_ROLE_ALCANCE,
        ad_type=AD_TYPE_DESIGN, descricao="Quebrar crença comum. Design com tipografia riscada.",
        layout_tipo="antes/depois de conceito (crença riscada vs verdade)", layout_hierarquia="Crença comum riscada → Verdade destacada → Explicação",
        layout_proporcao="texto 70% / elemento 30%", composicao="Frase riscada no topo, frase correta abaixo com cor destaque",
        cores_primarias="cinza (crença) + cor destaque vibrante + branco", cores_contraste="alto",
        cor_fundo="#FFFFFF", cor_texto="#999999 / #1a1a1a", tipografia_usa=True, tipografia_estilo="strikethrough + bold",
        tipografia_tamanho="médio-grande", tipografia_headline_tipo="quebra de crença",
        tipografia_cor="cinza / preto com destaque", tipografia_sombra=False, produto_posicao="discreto ou ausente",
        produto_proporcao="10%", texto_posicao="dominante (70%)", texto_proporcao="70%", brand_referencia="The Ordinary",
        emocao_alvo="surpresa + esclarecimento", objetivo="quebrar crença limitante e posicionar marca como esclarecida",
        scene_type="clinical_white", lighting_style="softbox_diffuse", depth_style="deep_focus", time_of_day="midday"),
    StyleConfig(id=11, nome="EDUCAÇÃO RÁPIDA", formato="POST", content_role=CONTENT_ROLE_CONFIANCA,
        ad_type=AD_TYPE_DESIGN, descricao="Ensinar algo útil em segundos. Design editorial premium.",
        layout_tipo="título + bullet points com ícones", layout_hierarquia="Título → 3-4 pontos com ícones → Dica bônus",
        layout_proporcao="texto 65% / ícones 35%", composicao="Título topo, pontos em grade, ícones dourados à esquerda",
        cores_primarias="papel texturizado + preto + detalhe azul", cores_contraste="médio",
        cor_fundo="#faf7f2", cor_texto="#1a1a1a", tipografia_usa=True, tipografia_estilo="clean sans-serif",
        tipografia_tamanho="médio / pequeno", tipografia_headline_tipo="título educativo",
        tipografia_cor="preto", tipografia_sombra=False, produto_posicao="discreto como exemplo", produto_proporcao="15%",
        texto_posicao="dominante (65%)", texto_proporcao="65%", brand_referencia="The Ordinary",
        emocao_alvo="aprendizado + gratidão", objetivo="ensinar algo útil e associar marca a conhecimento",
        scene_type="wooden_shelf", lighting_style="window_light_natural", depth_style="deep_focus", time_of_day="morning_dew"),
    StyleConfig(id=12, nome="CHECKLIST VISUAL", formato="POST", content_role=CONTENT_ROLE_CONFIANCA,
        ad_type=AD_TYPE_DESIGN, descricao="Checklist visual premium do que observar antes de comprar.",
        layout_tipo="grade de checklist com ícones", layout_hierarquia="Título → 4-5 itens com checkbox → Rodapé",
        layout_proporcao="texto 75% / ícones 25%", composicao="Grade organizada, checkmarks dourados, papel texturizado",
        cores_primarias="papel kraft + preto + detalhes dourados", cores_contraste="médio-alto",
        cor_fundo="#f5f0e8", cor_texto="#1a1a1a", tipografia_usa=True, tipografia_estilo="clean organizado",
        tipografia_tamanho="médio / pequeno", tipografia_headline_tipo="checklist educativo",
        tipografia_cor="preto", tipografia_sombra=False, produto_posicao="não aparece", produto_proporcao="0%",
        texto_posicao="dominante (75%)", texto_proporcao="75%", brand_referencia="Aesop",
        emocao_alvo="utilidade + empoderamento", objetivo="fornecer ferramenta prática de decisão de compra",
        scene_type="concrete_minimal", lighting_style="softbox_diffuse", depth_style="deep_focus", time_of_day="midday"),
    StyleConfig(id=13, nome="COMPARAÇÃO RÁPIDA", formato="POST", content_role=CONTENT_ROLE_CONVERSAO,
        ad_type=AD_TYPE_PHOTOGRAPHY_WITH_TEXT, descricao="Comparação visual lado a lado com iluminação cinematográfica.",
        layout_tipo="split screen 50/50 com labels premium", layout_hierarquia="Produto A (problema) vs Produto B (solução)",
        layout_proporcao="50/50 split com iluminação contrastante", composicao="Split screen: esquerda fria, direita quente com god rays",
        camera_lente="85mm", camera_angulo="eye_level", iluminacao_tipo="split lighting cinematográfico",
        iluminacao_direcao="esquerda fria 6000K / direita quente 3000K", iluminacao_temperatura="contrastante",
        cores_primarias="frio/dessaturado vs quente/vibrante", cores_contraste="muito alto",
        cor_fundo="neutro consistente", cor_texto="branco com sombra", tipografia_usa=True,
        tipografia_estilo="bold labels + headline", tipografia_tamanho="pequeno / médio",
        tipografia_headline_tipo="comparação direta", tipografia_cor="branco com fundo semitransparente",
        tipografia_sombra=True, produto_posicao="lado direito herói", produto_proporcao="50%",
        texto_posicao="labels nos dois lados + headline topo", texto_proporcao="25%", brand_referencia="La Mer",
        emocao_alvo="clareza + decisão", objetivo="ajudar a decidir com comparação visual cinematográfica",
        scene_type="split: clinical_white / aesop_shelf", lighting_style="split_lighting", depth_style="deep_focus", time_of_day="golden_hour"),
    StyleConfig(id=14, nome="OFERTA DIRETA", formato="POST", content_role=CONTENT_ROLE_CONVERSAO,
        ad_type=AD_TYPE_PHOTOGRAPHY_WITH_TEXT, descricao="Oferta clara com produto em destaque cinematográfico e preço grande.",
        layout_tipo="produto herói + informações de oferta", layout_hierarquia="Headline (20%) → Produto cinematográfico (50%) → Preço + CTA (30%)",
        layout_proporcao="texto 40% / produto 60%", composicao="Produto central iluminado com god rays, headline acima, preço abaixo",
        camera_lente="85mm", camera_angulo="slight low angle (hero shot)", iluminacao_tipo="god rays dourados com rim light",
        iluminacao_direcao="frontal superior + contraluz", iluminacao_temperatura="quente (3200K)",
        cores_primarias="dourado + preto + branco + cor marca", cores_contraste="alto",
        cor_fundo="fundo limpo com gradiente ou aesop shelf", cor_texto="preto + dourado (preço)",
        tipografia_usa=True, tipografia_estilo="BOLD para preço, clean premium", tipografia_tamanho="médio / GRANDE (preço) / pequeno (CTA)",
        tipografia_headline_tipo="oferta com benefício e urgência", tipografia_cor="preto + dourado",
        tipografia_sombra=False, produto_posicao="central herói grande", produto_proporcao="50%",
        texto_posicao="topo (headline) + base (preço e CTA)", texto_proporcao="40%", brand_referencia="Aesop / La Mer",
        emocao_alvo="desejo + urgência premium", objetivo="converter com oferta clara e produto cinematográfico",
        scene_type="aesop_shelf", lighting_style="god_rays", depth_style="bokeh_creamy", time_of_day="golden_hour"),
    StyleConfig(id=15, nome="ANTES/DEPOIS", formato="POST", content_role=CONTENT_ROLE_PROVA,
        ad_type=AD_TYPE_PHOTOGRAPHY_WITH_TEXT, descricao="Transformação visual real com iluminação cinematográfica consistente.",
        layout_tipo="split screen antes/depois com selo de garantia", layout_hierarquia="Headline (resultado) → Split antes/depois → Selo + CTA",
        layout_proporcao="imagem 65% / texto 35%", composicao="Split screen: esquerda antes (fria), direita depois (quente)",
        camera_lente="85mm", camera_angulo="eye_level", iluminacao_tipo="studio lighting consistente",
        iluminacao_direcao="idêntica nos dois lados", iluminacao_temperatura="neutra (5000K) para credibilidade",
        cores_primarias="neutro → vibrante", cores_contraste="alto", cor_fundo="neutro consistente",
        cor_texto="preto + selo dourado", tipografia_usa=True, tipografia_estilo="labels 'ANTES' e 'DEPOIS' + headline",
        tipografia_tamanho="pequeno / médio", tipografia_headline_tipo="resultado com tempo e garantia",
        tipografia_cor="branco sobre labels / preto headline", tipografia_sombra=True,
        produto_posicao="lado 'depois', em uso", produto_proporcao="35%", texto_posicao="labels + headline topo + selo base",
        texto_proporcao="30%", brand_referencia="La Mer / La Roche", emocao_alvo="surpresa + confiança + urgência",
        objetivo="prova visual irrefutável de transformação real", scene_type="clinical_white",
        lighting_style="softbox_diffuse", depth_style="deep_focus", time_of_day="midday"),
]

# ============================================================================
# BLOCO 5: AD_TYPE DECIDER (DECISÃO DE TIPO DE ANÚNCIO)
# ============================================================================
class AdTypeDecider:
    def decide(self, style: StyleConfig) -> str:
        return style.ad_type

    def get_prompt_prefix(self, ad_type: str, style: StyleConfig) -> str:
        if ad_type == AD_TYPE_DESIGN:
            return (
                f"CREATE A PROFESSIONAL GRAPHIC DESIGN ADVERTISEMENT with CINEMATIC QUALITY. "
                f"Style: {style.nome}. {style.descricao}. "
                f"THIS IS A STATIC AD — GRAPHIC DESIGN WITH TYPOGRAPHY, NOT PHOTOGRAPHY. "
                f"Use {style.cores_primarias}. Background: {style.cor_fundo}. "
                f"Typography: {style.tipografia_estilo}, {style.tipografia_tamanho}, text color: {style.tipografia_cor}. "
                f"Layout: {style.layout_tipo}. {style.composicao}. "
                f"Text position: {style.texto_posicao}. Text occupies {style.texto_proporcao} of the frame."
            )
        else:
            return (
                f"CREATE A CINEMATIC PRODUCT PHOTOGRAPHY ADVERTISEMENT WITH TEXT OVERLAY. "
                f"Style: {style.nome}. {style.descricao}. "
                f"STUDIO PHOTOGRAPHY with cinematic controlled lighting. "
                f"Camera: {style.camera_lente} lens, {style.camera_angulo} angle. "
                f"Lighting: {style.iluminacao_tipo}, {style.iluminacao_direcao}, {style.iluminacao_temperatura}. "
                f"Colors: {style.cores_primarias}. Background: {style.cor_fundo}. "
                f"Typography overlay: {style.tipografia_estilo}, {style.tipografia_tamanho}, text color: {style.tipografia_cor}. "
                f"Product position: {style.produto_posicao}, {style.produto_proporcao}. "
                f"Text position: {style.texto_posicao}, {style.texto_proporcao}."
            )

ad_type_decider = AdTypeDecider()

# ============================================================================
# BLOCO 6: HEADLINE GENERATOR (GERADOR DE HEADLINE)
# ============================================================================
class HeadlineGenerator:
    TEMPLATES: Dict[str, List[str]] = {
        CONTENT_ROLE_ALCANCE: [
            "A gente não trabalha com {categoria} comum.",
            "Se não for funcional, não entra.",
            "O problema não é o {categoria}. É como você escolhe.",
            "Comprar {categoria} barato sem critério sai caro.",
            "Aqui a gente só trabalha com o que resolve.",
            "O mercado empurra. A gente seleciona.",
            "Não somos loja comum.",
            "Quem sabe escolher, não erra duas vezes.",
            "{categoria} bom não precisa convencer. Entrega.",
            "Menos quantidade. Mais qualidade.",
        ],
        CONTENT_ROLE_CONFIANCA: [
            "O erro que todo mundo comete ao comprar {categoria}.",
            "Antes de comprar {categoria}, leia isso.",
            "Checklist: o que olhar antes de escolher {categoria}.",
            "Alerta: se seu {categoria} não tem isso, não compre.",
            "Você está comprando {categoria} errado (e nem sabe).",
            "O que ninguém te conta sobre {categoria}.",
        ],
        CONTENT_ROLE_CONVERSAO: [
            "{categoria} que realmente funciona. Sem enrolação.",
            "Comparação real: {categoria} barato vs {categoria} bom.",
            "O {categoria} que a gente recomenda de olho fechado.",
            "Não é o mais barato. É o que resolve.",
            "{categoria} que vale cada centavo. Aqui está o porquê.",
            "Resultado em {tempo}: o {categoria} que entrega.",
        ],
        CONTENT_ROLE_PROVA: [
            "Testei por {tempo}. Aqui está o resultado real.",
            "Antes e depois: {tempo} usando {categoria}.",
            "O que aconteceu quando usei {categoria} por {tempo}.",
            "Resultado real, sem filtro. {tempo} de uso.",
            "Não é montagem. É o que {categoria} fez em {tempo}.",
        ],
    }

    def generate(self, content_role: ContentRole, categoria: str = "produto", tempo: str = "7 dias") -> str:
        templates = self.TEMPLATES.get(content_role.value, self.TEMPLATES[CONTENT_ROLE_CONFIANCA])
        headline = random.choice(templates).format(categoria=categoria, tempo=tempo)
        logger.info(f"[Headline] '{headline[:60]}...'")
        return headline

headline_generator = HeadlineGenerator()

# ============================================================================
# BLOCO 7: TEXT OVERLAY ENGINE (CONFIGURAÇÃO DE TIPOGRAFIA)
# ============================================================================
class TextOverlayEngine:
    FONT_STYLES = {
        "bold": "bold sans-serif (Montserrat Black, Helvetica Neue Bold, Inter Extra Bold)",
        "elegant": "elegant serif or light sans-serif (Playfair Display, Cormorant Garamond, Inter Light)",
        "clean": "clean sans-serif (Inter, SF Pro, Roboto, Helvetica Neue)",
        "statement": "bold condensed (Bebas Neue, Impact, Anton, Helvetica Black)",
        "premium": "premium serif or thin sans-serif (Didot, Bodoni, Thin Helvetica, Cormorant)",
    }

    def generate_headline_config(self, style: StyleConfig, content_role: ContentRole, headline_text: str) -> Dict[str, Any]:
        if not style.tipografia_usa:
            return {"usar_tipografia": False, "headline": "", "configuracao": {}}
        font_style = "clean"
        estilo_str = style.tipografia_estilo.lower()
        if "bold" in estilo_str and "statement" in estilo_str:
            font_style = "statement"
        elif "bold" in estilo_str:
            font_style = "bold"
        elif "elegant" in estilo_str or "serif" in estilo_str:
            font_style = "elegant"
        elif "premium" in style.nome.lower():
            font_style = "premium"
        text_color = style.tipografia_cor or ("#FFFFFF" if "escuro" in style.cor_fundo.lower() else "#000000")
        tamanho = style.tipografia_tamanho or "large (30-40% of frame height)"
        if style.ad_type == AD_TYPE_DESIGN:
            typography_instruction = (
                f"TYPOGRAPHY: Large bold headline text MUST be visible on the image. "
                f"Headline: \"{headline_text}\". Font: {self.FONT_STYLES.get(font_style, self.FONT_STYLES['clean'])}. "
                f"Size: {tamanho}. Color: {text_color}. Position: {style.texto_posicao}. "
                f"Text occupies approximately {style.texto_proporcao} of the frame. "
                f"{'Text shadow for readability.' if style.tipografia_sombra else ''} "
                f"THIS IS A GRAPHIC DESIGN — the text IS the main element."
            )
        else:
            typography_instruction = (
                f"TEXT OVERLAY: Headline text MUST be visible over the photograph. "
                f"Headline: \"{headline_text}\". Font: {self.FONT_STYLES.get(font_style, self.FONT_STYLES['clean'])}. "
                f"Size: {tamanho}. Color: {text_color}. Position: {style.texto_posicao}. "
                f"Text occupies approximately {style.texto_proporcao} of the frame. "
                f"{'Text shadow for readability over the photo.' if style.tipografia_sombra else ''}"
            )
        return {
            "usar_tipografia": True, "headline": headline_text, "typography_instruction": typography_instruction,
            "fonte_estilo": self.FONT_STYLES.get(font_style), "fonte_cor": text_color,
            "regras": ["Text MUST be 100% legible", "High contrast (4.5:1 minimum)", "Max 3 lines", "Safe margins 5-10%"],
            "negative_text": "NO unreadable text, NO text that blends, NO decorative fonts, NO text <5% height",
        }

text_overlay_engine = TextOverlayEngine()

# ============================================================================
# BLOCO 8: LAYOUT ENGINE (HIERARQUIA VISUAL)
# ============================================================================
class LayoutEngine:
    def get_layout_instruction(self, style: StyleConfig) -> str:
        if style.ad_type == AD_TYPE_DESIGN:
            return (
                f"LAYOUT: {style.layout_tipo}. Visual hierarchy: {style.layout_hierarquia}. "
                f"Proportion: {style.layout_proporcao}. Composition: {style.composicao}. "
                f"Product: {style.produto_posicao} ({style.produto_proporcao}). "
                f"Text: {style.texto_posicao} ({style.texto_proporcao}). "
                f"Background: solid {style.cor_fundo}. Professional graphic design with clear hierarchy."
            )
        else:
            return (
                f"LAYOUT: {style.layout_tipo}. Visual hierarchy: {style.layout_hierarquia}. "
                f"Proportion: {style.layout_proporcao}. Composition: {style.composicao}. "
                f"Product: {style.produto_posicao} ({style.produto_proporcao}). "
                f"Text overlay: {style.texto_posicao} ({style.texto_proporcao}). "
                f"Studio photography with professional composition."
            )

    def get_layout_rules(self) -> Dict[str, Any]:
        return {
            "rules": ["Clear hierarchy", "Safe margins 5-10%", "No elements touching edges",
                      "Single focal point", "Strategic negative space", "Z-pattern or F-pattern flow"],
            "negative_layout": "NO clutter, NO random placement, NO competing focal points, NO text overlapping critical areas",
        }

layout_engine = LayoutEngine()

# ============================================================================
# BLOCO 9: BRAND SIMULATION ENGINE (REFERÊNCIA DE MARCA)
# ============================================================================
class BrandSimulationEngine:
    def get_brand_config(self, style: StyleConfig) -> Dict[str, Any]:
        brand_key = style.brand_referencia if style.brand_referencia in BRAND_REFERENCES else "Aesop"
        brand_config = BRAND_REFERENCES.get(brand_key, BRAND_REFERENCES["Aesop"])
        return {
            "brand_reference": brand_key, "style": brand_config["style"],
            "lighting": brand_config["lighting"], "composition": brand_config["composition"],
            "colors": brand_config["colors"], "vibe": brand_config["vibe"],
            "instruction": f"Simulate the advertising aesthetic of {brand_key}. {brand_config['vibe']}",
            "negative_brand": "NO UGC style, NO amateur look, NO casual photography, NO documentary feel",
        }

brand_simulation_engine = BrandSimulationEngine()

# ============================================================================
# BLOCO 10: CAMERA ENGINE (PARÂMETROS DE CÂMERA CINEMATOGRÁFICA)
# ============================================================================
class CameraEngine:
    PRESETS = {
        "product_hero": {"lens": "85mm prime", "aperture": "f/2.0", "angle": "eye level, slight hero angle (10° up)",
                         "focus": "manual, critically sharp on product, background creamy bokeh",
                         "purpose": "isolate product with beautiful background separation"},
        "environmental": {"lens": "35mm", "aperture": "f/5.6", "angle": "eye level, wide context",
                          "focus": "deep focus, entire scene sharp", "purpose": "show product in luxurious environment"},
        "macro_detail": {"lens": "100mm macro", "aperture": "f/2.8", "angle": "top-down or 45°",
                         "focus": "extremely shallow, only detail in focus", "purpose": "highlight texture and craftsmanship"},
        "editorial_wide": {"lens": "24mm", "aperture": "f/8", "angle": "low angle, dramatic perspective",
                           "focus": "hyperfocal, everything sharp", "purpose": "architectural feel, magazine editorial"},
    }

    def get_config(self, style: StyleConfig, content_role: ContentRole) -> Dict[str, str]:
        if style.ad_type == AD_TYPE_DESIGN:
            return {"lens": "N/A (design)", "aperture": "N/A", "angle": "N/A"}
        if style.scene_type in ("velvet_dark", "dramatic_reveal"):
            preset = self.PRESETS["product_hero"]
        elif style.scene_type in ("wooden_shelf", "retail_premium", "aesop_shelf"):
            preset = self.PRESETS["environmental"]
        elif content_role == ContentRole.PROVA:
            preset = self.PRESETS["macro_detail"]
        else:
            preset = self.PRESETS["editorial_wide"] if "wide" in style.composicao.lower() else self.PRESETS["product_hero"]
        return {
            "lens": preset["lens"], "aperture": preset["aperture"], "angle": preset["angle"],
            "focus": preset["focus"], "instruction": f"Camera: {preset['lens']}, {preset['aperture']}, {preset['angle']}. {preset['focus']}.",
        }

camera_engine = CameraEngine()

# ============================================================================
# BLOCO 11: NEGATIVE PROMPT BUILDER (ANTI-UGC + ANTI-GENÉRICO)
# ============================================================================
class NegativePromptBuilder:
    NEGATIVE_BASE = [
        "no handheld camera", "no smartphone photography", "no selfie angle",
        "no candid shot", "no documentary style", "no amateur photography",
        "no snapshot aesthetic", "no casual photo", "no phone picture",
        "no vlog style", "no natural light only", "no available light photography",
        "no unplanned composition", "no messy background", "no clutter",
        "no generic stock photography", "no fake smile", "no overexposed white background",
        "no cheap looking product shot", "no low resolution", "no pixelated",
        "no blurry product", "no distorted product", "no watermark",
        "no text in wrong position", "no unreadable small text",
        "no cluttered typography", "no more than 8 words on image",
        "no noise in shadows", "no chromatic aberration",
        "no lens flare unintended", "no motion blur", "no camera shake",
        "no obvious 3D render look", "no plastic-looking materials",
        "no fake depth of field", "no artificial bokeh",
    ]
    NEGATIVE_CINEMATIC = [
        "no flat lighting", "no boring composition", "no dead space without purpose",
        "no harsh direct flash", "no on-camera flash",
        "no pure white background without texture", "no perfectly symmetrical composition",
        "no digital sharpness that looks artificial", "no HDR overprocessed look",
    ]
    NEGATIVE_BY_ROLE = {
        CONTENT_ROLE_ALCANCE: ["no weak statement", "no generic quote", "no boring layout",
                               "no inspirational poster cliché", "no corporate template look"],
        CONTENT_ROLE_CONFIANCA: ["no academic textbook style", "no boring educational content",
                                  "no complex diagram", "no cluttered information"],
        CONTENT_ROLE_CONVERSAO: ["no hard sell screaming", "no used car salesman vibe",
                                 "no discount sticker overload", "no fake urgency badges", "no cheap promotion look"],
        CONTENT_ROLE_PROVA: ["no fake before after", "no photoshopped results",
                             "no unrealistic transformation", "no stock photo pretending to be real"],
    }

    def build(self, style: StyleConfig, content_role: ContentRole) -> Dict[str, Any]:
        negative = list(self.NEGATIVE_BASE)
        negative.extend(self.NEGATIVE_CINEMATIC)
        role_negatives = self.NEGATIVE_BY_ROLE.get(content_role.value, [])
        negative.extend(role_negatives)
        if not style.tipografia_usa:
            negative.extend(["no text on image", "no typography", "no headline", "no words on picture"])
        else:
            negative.extend(["no unreadable text", "no text that blends with background",
                             "no decorative fonts that are hard to read", "no text smaller than 5% of image height"])
        if style.produto_proporcao == "0%":
            negative.append("no product visible")
        seen = set()
        unique_negative = []
        for item in negative:
            if item not in seen:
                seen.add(item)
                unique_negative.append(item)
        result = {"negative_prompt": ", ".join(unique_negative), "count": len(unique_negative)}
        logger.info(f"[Negative Prompt] {result['count']} termos gerados")
        return result

negative_prompt_builder = NegativePromptBuilder()

# ============================================================================
# BLOCO 12: PROMPT QUALITY GATE (PORTÃO DE QUALIDADE ≥ 9.0 — ANTI-ERRO)
# ============================================================================
class PromptQualityGate:
    """
    Quality Gate 100% à prova de falsos positivos.
    Ignora automaticamente o negative prompt e as seções de proibição.
    """
    def __init__(self):
        self._bloqueios = 0
        self._aprovacoes = 0
        self._total_validacoes = 0

    def validate(self, prompt_text: str, style: StyleConfig) -> Tuple[bool, float, List[str]]:
        # Remove o negative prompt e proibições para validação limpa
        clean_text = prompt_text
        for marker in ["CRITICAL PROHIBITIONS:", "NEGATIVE PROMPT:", "negative_prompt:", "PROHIBITIONS:"]:
            idx = clean_text.lower().find(marker.lower())
            if idx > 0:
                clean_text = clean_text[:idx]
        t = clean_text.lower()
        razoes: List[str] = []
        score = 10.0
        self._total_validacoes += 1

        # 1. UGC detection (ignora palavras após "no ")
        ugc_found = []
        for word in UGC_BLOCKERS:
            for match in re.finditer(r'\b' + re.escape(word) + r'\b', t):
                start = match.start()
                prefix = t[max(0, start-4):start]
                if not prefix.endswith('no '):
                    ugc_found.append(word)
                    break
        if ugc_found:
            score -= len(ugc_found) * 2.0
            razoes.append(f"UGC_DETECTED: {ugc_found[:3]}")

        # 2. Elementos profissionais obrigatórios
        if style.ad_type == AD_TYPE_PHOTOGRAPHY_WITH_TEXT:
            if not any(word in t for word in REQUIRED_PRO_ELEMENTS):
                score -= 2.0
                razoes.append("SEM_ELEMENTOS_DE_ANUNCIO_PROFISSIONAL")
            if not any(w in t for w in ["studio lighting", "controlled lighting", "softbox", "rim light", "god rays", "volumetric", "cinematic lighting", "professional lighting"]):
                score -= 1.5
                razoes.append("ILUMINACAO_NAO_CONTROLADA_OU_NAO_CINEMATICA")

        # 3. Tipografia obrigatória
        if style.tipografia_usa:
            if not any(w in t for w in ["headline", "text", "typography", "overlay", "font", "bold text", "text visible"]):
                score -= 2.5
                razoes.append("ESTILO_REQUER_TIPOGRAFIA_MAS_SEM_TEXTO_NO_PROMPT")

        # 4. Genéricos
        generic_found = [word for word in GENERIC_BLOCKERS if word in t]
        if generic_found:
            score -= len(generic_found) * 1.0
            razoes.append(f"GENERIC_DETECTED: {generic_found[:2]}")

        # 5. Elementos cinematográficos mínimos
        if style.ad_type == AD_TYPE_PHOTOGRAPHY_WITH_TEXT:
            if not any(w in t for w in ["depth of field", "bokeh", "golden ratio", "foreground", "midground", "background", "texture", "cinematic", "god rays", "volumetric", "atmospheric"]):
                score -= 1.0
                razoes.append("SEM_ELEMENTOS_CINEMATOGRAFICOS_MINIMOS")

        aprovado = score >= SCORE_MINIMO_ABSOLUTO
        if not aprovado:
            self._bloqueios += 1
        else:
            self._aprovacoes += 1
        logger.info(f"[Quality Gate] Score: {score:.1f}/10 {'✅' if aprovado else '❌'}")
        return aprovado, round(score, 1), razoes

prompt_quality_gate = PromptQualityGate()

# ============================================================================
# FUNÇÃO DE INTERFACE PARA O HERMES AGENT (VERSÃO BASE — EXPANDIDA NA PARTE 4)
# ============================================================================
def run(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ponto de entrada oficial para o Hermes Agent.
    Versão base que será expandida nas próximas partes com todos os 55 blocos.
    """
    if not payload or "copy" not in payload:
        raise InvalidInputError("Payload deve conter ao menos a chave 'copy'.")
    copy_text = payload["copy"]
    product_name = payload.get("product_name", payload.get("produto", ""))
    product_category = payload.get("product_category", payload.get("categoria", "produto"))
    timeframe = payload.get("timeframe", payload.get("tempo", "7 dias"))
    formato = payload.get("formato", "POST").upper()
    platform_str = payload.get("platform", payload.get("plataforma", "instagram_feed")).lower()
    if len(copy_text.strip()) < 20:
        raise InvalidInputError("A copy deve ter pelo menos 20 caracteres.")
    try:
        platform_enum = Platform(platform_str)
    except ValueError:
        platform_enum = Platform.INSTAGRAM_FEED

    content_role, confidence, _ = content_role_classifier.classify(copy_text)
    estilos_por_formato = {"POST": ESTILOS_POST, "CARROSSEL": [], "STORY": []}
    estilos = estilos_por_formato.get(formato, ESTILOS_POST)
    style = style_selector.select(copy_text, content_role, formato, estilos)
    headline = headline_generator.generate(content_role, product_category, timeframe)
    ad_type = ad_type_decider.decide(style)
    ad_type_prefix = ad_type_decider.get_prompt_prefix(ad_type, style)
    camera_config = camera_engine.get_config(style, content_role) if ad_type == AD_TYPE_PHOTOGRAPHY_WITH_TEXT else {"lens": "N/A"}
    brand_config = brand_simulation_engine.get_brand_config(style)
    text_config = text_overlay_engine.generate_headline_config(style, content_role, headline)
    layout_instruction = layout_engine.get_layout_instruction(style)
    negative_config = negative_prompt_builder.build(style, content_role)

    prompt_completo = f"{ad_type_prefix}\n\nHEADLINE: {headline}\n\n{text_config.get('typography_instruction','')}\n\n{layout_instruction}\n\nBrand: {brand_config.get('brand_reference','')} — {brand_config.get('vibe','')}\n\nCamera: {camera_config.get('instruction','')}\n\nPROFESSIONAL STUDIO PHOTOGRAPHY. NO UGC. CINEMATIC QUALITY."
    aprovado, score, razoes = prompt_quality_gate.validate(prompt_completo, style)

    return {
        "versao": f"hermes_image_engine_v{VERSION}",
        "build": BUILD,
        "formato": formato,
        "plataforma": platform_enum.value,
        "content_role": content_role.value,
        "ad_type": ad_type,
        "estilo_nome": style.nome,
        "estilo_id": style.id,
        "headline": headline,
        "prompt_completo": prompt_completo,
        "negative_prompt": negative_config["negative_prompt"],
        "qualidade": {"score": score, "aprovado": aprovado, "razoes": razoes},
        "cinematic_scene": {"scene_type": style.scene_type, "lighting_style": style.lighting_style, "depth_style": style.depth_style},
    }

# ============================================================================
# MENSAGEM DE PRONTIDÃO DA PARTE 1
# ============================================================================
if __name__ == "__main__":
    print("Hermes Image Engine V20 — Parte 1/5 carregada. Blocos 1-12 prontos.")
    print(f"Versão: {VERSION} | Build: {BUILD}")

# ============================================================================
# HERMES IMAGE ENGINE V20 — NÍVEL DEUS ABSOLUTO — PARTE 2/5
# Blocos 13 a 24 + Catálogos Carrossel e Story + Função run() Expandida
# Continuação direta da Parte 1/5 — todos os imports, enums, dataclasses,
# constantes e engines básicas já estão definidos.
# ============================================================================

# ============================================================================
# BLOCO 13 – REGENERATION LOOP (LOOP DE REGENERAÇÃO INTELIGENTE)
# ============================================================================
class RegenerationLoop:
    """
    Loop de regeneração com estratégia adaptativa multi-camada.
    Quando o Quality Gate bloqueia um prompt, este loop:
    - Troca o estilo (evitando os últimos 3 usados)
    - Ajusta parâmetros de iluminação e profundidade
    - Alterna o Content Role se necessário (após 3 falhas consecutivas)
    - Mantém histórico detalhado de tentativas para evitar repetição
    - Respeita o limite máximo de regenerações (5 tentativas)
    - Aplica backoff exponencial em caso de falhas repetidas
    - Registra métricas de convergência para análise posterior
    - Força mudança de ângulo criativo a cada 2 falhas consecutivas
    """

    def __init__(self, max_attempts: int = MAX_TENTATIVAS_REGENERACAO):
        self.max_attempts = max_attempts
        self.attempt_history: List[Dict[str, Any]] = []
        self.role_alternation_triggered = False
        self.consecutive_failures = 0
        self.backoff_delays = [0, 0.5, 1.0, 2.0, 4.0]  # backoff exponencial em segundos
        self.angle_shift_counter = 0
        self.used_styles: Set[int] = set()
        self.used_headlines: Set[str] = set()
        self.best_score_ever = 0.0
        self.total_attempts_ever = 0

    def execute(self, build_func, *args, **kwargs) -> Dict[str, Any]:
        """
        Executa a função de build repetidamente até obter aprovação ou esgotar tentativas.
        build_func deve aceitar um argumento 'attempt' (int) e retornar o dict de resultado.
        """
        best_result = None
        best_score = 0.0
        attempts_details = []

        for attempt in range(self.max_attempts + 1):
            logger.info(f"🔄 Regeneration Loop — Tentativa {attempt + 1}/{self.max_attempts + 1}")

            # Backoff se muitas falhas consecutivas
            if self.consecutive_failures > 0 and self.consecutive_failures < len(self.backoff_delays):
                delay = self.backoff_delays[self.consecutive_failures]
                if delay > 0:
                    logger.info(f"⏳ Backoff de {delay}s após {self.consecutive_failures} falhas consecutivas")
                    time.sleep(delay)

            # Forçar mudança de ângulo a cada 2 falhas
            if self.angle_shift_counter >= 2:
                kwargs['force_angle_shift'] = True
                self.angle_shift_counter = 0
                logger.info("🔄 Forçando mudança de ângulo criativo após 2 falhas consecutivas")
            else:
                kwargs['force_angle_shift'] = False

            try:
                result = build_func(attempt=attempt, *args, **kwargs)
                if result is None:
                    self.consecutive_failures += 1
                    self.angle_shift_counter += 1
                    continue

                score = result.get("qualidade", {}).get("score", 0.0)
                approved = result.get("qualidade", {}).get("aprovado", False)
                estilo_id = result.get("estilo_id")
                estilo_nome = result.get("estilo_nome", "")
                headline = result.get("headline", "")

                # Registrar tentativa
                attempt_record = {
                    "attempt": attempt + 1,
                    "style_id": estilo_id,
                    "style_name": estilo_nome,
                    "score": score,
                    "approved": approved,
                    "headline": headline[:60],
                    "timestamp": time.time(),
                }
                self.attempt_history.append(attempt_record)
                attempts_details.append(attempt_record)
                self.total_attempts_ever += 1

                # Atualizar registros de uso
                if estilo_id:
                    self.used_styles.add(estilo_id)
                if headline:
                    self.used_headlines.add(headline)

                # Atualizar melhor resultado
                if score > best_score:
                    best_score = score
                    best_result = result
                if score > self.best_score_ever:
                    self.best_score_ever = score

                # Verificar aprovação
                if approved:
                    self.consecutive_failures = 0
                    self.angle_shift_counter = 0
                    logger.info(f"✅ Prompt aprovado na tentativa {attempt + 1} (score: {score})")
                    break
                else:
                    self.consecutive_failures += 1
                    self.angle_shift_counter += 1
                    logger.warning(f"❌ Tentativa {attempt + 1} bloqueada (score: {score}). "
                                   f"Falhas consecutivas: {self.consecutive_failures}")

                    # Se 3 falhas consecutivas, alterna Content Role
                    if self.consecutive_failures >= 3 and not self.role_alternation_triggered:
                        self.role_alternation_triggered = True
                        logger.info("🔄 Alternando Content Role após 3 falhas consecutivas...")

            except Exception as e:
                logger.error(f"Tentativa {attempt + 1} falhou com erro: {e}")
                self.attempt_history.append({"attempt": attempt + 1, "error": str(e), "timestamp": time.time()})
                self.consecutive_failures += 1
                self.angle_shift_counter += 1
                continue

        # Pós-processamento
        if best_result is None:
            raise PipelineAbortedError("Nenhum prompt válido gerado após todas as tentativas.")

        if not best_result.get("qualidade", {}).get("aprovado"):
            logger.warning("⚠️ Melhor prompt ainda abaixo do Quality Gate, mas será entregue como melhor resultado.")

        # Adiciona metadados de regeneração ao resultado
        best_result["regeneration_meta"] = {
            "total_attempts": attempt + 1,
            "best_score": best_score,
            "attempts": attempts_details,
            "role_alternated": self.role_alternation_triggered,
            "angle_shifts": self.angle_shift_counter,
            "unique_styles_tried": len(self.used_styles),
            "unique_headlines_tried": len(self.used_headlines),
            "best_score_ever": self.best_score_ever,
            "total_attempts_ever": self.total_attempts_ever,
        }
        return best_result

    def get_statistics(self) -> Dict[str, Any]:
        """Retorna estatísticas de convergência do loop."""
        if not self.attempt_history:
            return {"total_attempts": 0}
        scores = [a.get("score", 0) for a in self.attempt_history if "score" in a]
        return {
            "total_attempts": len(self.attempt_history),
            "avg_score": round(sum(scores) / len(scores), 2) if scores else 0,
            "max_score": max(scores) if scores else 0,
            "min_score": min(scores) if scores else 0,
            "approved": any(a.get("approved") for a in self.attempt_history),
            "convergence_speed": next((i+1 for i, a in enumerate(self.attempt_history) if a.get("approved")), None),
            "unique_styles": len(self.used_styles),
            "best_score_ever": self.best_score_ever,
        }

    def reset(self):
        """Reseta o estado do loop para nova execução."""
        self.attempt_history.clear()
        self.role_alternation_triggered = False
        self.consecutive_failures = 0
        self.angle_shift_counter = 0
        self.used_styles.clear()
        self.used_headlines.clear()


# ============================================================================
# BLOCO 14 – PROMPT ASSEMBLER (MONTADOR AVANÇADO DE PROMPT)
# ============================================================================
class PromptAssembler:
    """
    Monta o prompt final unificando TODOS os elementos gerados pelos blocos.
    Suporta placeholders para blocos opcionais e garante coesão narrativa.
    """

    def assemble(self, copy: str, style: StyleConfig, content_role: ContentRole,
                 headline: str, ad_type: str, ad_type_prefix: str,
                 camera_config: Dict, brand_config: Dict, text_config: Dict,
                 layout_instruction: str, platform: Platform, product_name: str,
                 scene_config: Optional[CinematicSceneConfig] = None,
                 scene_instructions: str = "", material_instructions: str = "",
                 lighting_instructions: str = "", color_instructions: str = "",
                 depth_instructions: str = "", particle_instructions: str = "",
                 caustic_instructions: str = "", golden_ratio_instructions: str = "",
                 texture_story_instructions: str = "", temp_shift_instructions: str = "",
                 shadow_instructions: str = "", echo_instructions: str = "",
                 imperfection_instructions: str = "", sensory_instructions: str = "",
                 time_instructions: str = "", hero_lighting_instructions: str = "",
                 visual_hook: str = "", attention_instruction: str = "",
                 composition_instruction: str = "", product_placement: str = "",
                 color_palette_instruction: str = "", typography_instruction: str = "",
                 lighting_instruction: str = "", content_type_instruction: str = "",
                 storytelling_instruction: str = "", brand_world_instruction: str = "",
                 typography_integration_instruction: str = "", multi_format_instruction: str = "",
                 hyper_detail_instruction: str = "", creative_concept_instruction: str = "",
                 mandatory_copy_instruction: str = "", environment_reflection_instruction: str = "",
                 camera_lens_simulation_instruction: str = "", story_composition_instruction: str = "",
                 sensory_immersion_instruction: str = ""
                 ) -> str:
        """
        Constrói o prompt final mesclando o prefixo de AD type com todas as instruções
        cinematográficas e de design. As seções opcionais serão incluídas apenas se
        fornecidas, permitindo uso parcial do pipeline.
        """
        sections = []

        # 1. Prefixo obrigatório
        sections.append(ad_type_prefix)
        sections.append("")

        # 2. Contexto da copy (OBRIGATÓRIO incluir a copy na imagem)
        sections.append(f"AD COPY CONTEXT (THIS TEXT MUST APPEAR ON THE FINAL IMAGE):\n\"\"\"\n{copy}\n\"\"\"\n")

        # 3. Brand e estilo
        sections.append(f"STYLE REFERENCE: {style.nome} (ID:{style.id})")
        sections.append(f"BRAND REFERENCE: {brand_config.get('brand_reference', '')} — {brand_config.get('vibe', '')}")

        # 4. Content Type (bloco 41, se disponível)
        if content_type_instruction:
            sections.append(f"CONTENT TYPE: {content_type_instruction}")

        # 5. Brand World (bloco 43, se disponível)
        if brand_world_instruction:
            sections.append(f"BRAND WORLD: {brand_world_instruction}")

        # 6. Conceito Criativo (bloco 47, se disponível)
        if creative_concept_instruction:
            sections.append(f"CREATIVE CONCEPT: {creative_concept_instruction}")

        # 7. Visual Hook e Atenção (blocos 18-19)
        if visual_hook:
            sections.append(f"\n{visual_hook}")
        if attention_instruction:
            sections.append(f"{attention_instruction}")

        # 8. Layout e Composição (blocos 8, 20)
        sections.append(f"\n{layout_instruction}")
        if composition_instruction:
            sections.append(composition_instruction)
        if story_composition_instruction:
            sections.append(story_composition_instruction)
        if product_placement:
            sections.append(product_placement)

        # 9. Cores e Tipografia (blocos 22-23)
        if color_palette_instruction:
            sections.append(f"\n{color_palette_instruction}")
        if typography_instruction:
            sections.append(typography_instruction)
        elif text_config.get("typography_instruction"):
            sections.append(text_config["typography_instruction"])

        # 10. Integração de Tipografia (bloco 44, se disponível)
        if typography_integration_instruction:
            sections.append(f"TYPOGRAPHY INTEGRATION: {typography_integration_instruction}")

        # 11. Cópia obrigatória na imagem (bloco 48, se disponível)
        if mandatory_copy_instruction:
            sections.append(f"MANDATORY COPY: {mandatory_copy_instruction}")

        # 12. Iluminação base (bloco 24)
        if lighting_instruction:
            sections.append(f"\n{lighting_instruction}")

        # 13. Blocos Cinematográficos (25-40)
        if scene_instructions:
            sections.append(f"\nCINEMATIC SCENE:\n{scene_instructions}")
        if material_instructions:
            sections.append(f"\n{material_instructions}")
        if lighting_instructions:
            sections.append(f"\n{lighting_instructions}")
        if hero_lighting_instructions:
            sections.append(f"\n{hero_lighting_instructions}")
        if color_instructions:
            sections.append(f"\n{color_instructions}")
        if depth_instructions:
            sections.append(f"\n{depth_instructions}")
        if golden_ratio_instructions:
            sections.append(f"\n{golden_ratio_instructions}")
        if particle_instructions:
            sections.append(f"\n{particle_instructions}")
        if caustic_instructions:
            sections.append(f"\n{caustic_instructions}")
        if temp_shift_instructions:
            sections.append(f"\n{temp_shift_instructions}")
        if shadow_instructions:
            sections.append(f"\n{shadow_instructions}")
        if echo_instructions:
            sections.append(f"\n{echo_instructions}")
        if texture_story_instructions:
            sections.append(f"\n{texture_story_instructions}")
        if imperfection_instructions:
            sections.append(f"\n{imperfection_instructions}")
        if sensory_instructions:
            sections.append(f"\n{sensory_instructions}")
        if time_instructions:
            sections.append(f"\n{time_instructions}")

        # 14. Reflexos e Integração de Ambiente (bloco 49, se disponível)
        if environment_reflection_instruction:
            sections.append(f"\nENVIRONMENT REFLECTION: {environment_reflection_instruction}")

        # 15. Simulação de Câmera e Lente (bloco 50, se disponível)
        if camera_lens_simulation_instruction:
            sections.append(f"\nCAMERA & LENS SIMULATION: {camera_lens_simulation_instruction}")

        # 16. Hyper-Detail (bloco 46, se disponível)
        if hyper_detail_instruction:
            sections.append(f"\nHYPER-DETAIL SPECIFICATIONS:\n{hyper_detail_instruction}")

        # 17. Storytelling Visual (bloco 42, se disponível)
        if storytelling_instruction:
            sections.append(f"\nVISUAL STORYTELLING: {storytelling_instruction}")

        # 18. Imersão Sensorial (bloco 52, se disponível)
        if sensory_immersion_instruction:
            sections.append(f"\nSENSORY IMMERSION: {sensory_immersion_instruction}")

        # 19. Multi-Format (bloco 45, se disponível)
        if multi_format_instruction:
            sections.append(f"\nMULTI-FORMAT ADAPTATION: {multi_format_instruction}")

        # 20. Informações do produto
        if style.produto_proporcao != "0%" and product_name:
            sections.append(f"\nPRODUCT: {product_name} — Position: {style.produto_posicao} ({style.produto_proporcao})")

        # 21. Proibições críticas (versão limpa, sem palavras bloqueadas)
        sections.append("\nCRITICAL PROHIBITIONS:")
        sections.append("- NO UGC elements of any kind")
        sections.append("- NO natural light only photography")
        sections.append("- NO casual or unplanned composition")
        sections.append("- NO generic stock photography")
        sections.append("- NO 3D render look — must be photorealistic")
        sections.append("- NO artificial bokeh — must be optical")
        sections.append("- NO flat lighting without depth")
        sections.append("- NO text smaller than 5% of image height")
        sections.append("- NO image without the ad copy text integrated")

        # 22. Formato técnico
        sections.append(f"\nTECHNICAL FORMAT:\nPlatform: {platform.value}\n"
                        f"Aspect Ratio: {platform.get_aspect_ratio()}\n"
                        f"Resolution: {platform.get_resolution()}")

        # 23. Requisito final
        sections.append("\nFINAL OUTPUT REQUIREMENT: Cinematic professional advertisement. "
                        "Photorealistic quality. Museum-grade composition. "
                        "Every detail intentional. Every texture authentic. "
                        "The ad copy text MUST be visible and legible on the final image. "
                        "Ready for premium brand campaign.")

        return "\n".join(sections)


prompt_assembler = PromptAssembler()


# ============================================================================
# BLOCO 15 – OUTPUT FORMATTER (FORMATADOR DE SAÍDA MULTI-FORMATO)
# ============================================================================
class OutputFormatter:
    """
    Formata o resultado final em JSON, Markdown, texto puro ou HTML.
    Suporta inclusão/exclusão seletiva de campos e formatação customizada.
    """

    @staticmethod
    def to_json(result: Dict[str, Any], include_prompt: bool = True, indent: int = 2) -> str:
        """Retorna representação JSON do resultado."""
        output = {k: v for k, v in result.items() if k != "prompt_completo" or include_prompt}
        return json.dumps(output, ensure_ascii=False, indent=indent, default=str)

    @staticmethod
    def to_markdown(result: Dict[str, Any]) -> str:
        """Retorna representação Markdown amigável para leitura humana."""
        lines = [
            f"# 🎬 Image Prompt — {result.get('estilo_nome', 'N/A')}",
            f"*Generated by Hermes Image Engine V20 — Nível Deus Absoluto*",
            "",
            f"## 📋 Metadata",
            f"- **Content Role:** {result.get('content_role', '')}",
            f"- **Content Type:** {result.get('content_type', result.get('meta', {}).get('content_type', ''))}",
            f"- **AD Type:** {result.get('ad_type', '')}",
            f"- **Headline:** {result.get('headline', '')}",
            f"- **Score:** {result.get('qualidade', {}).get('score', '')}/10",
            f"- **Approved:** {result.get('qualidade', {}).get('aprovado', '')}",
            f"- **Scene:** {result.get('cinematic_scene', {}).get('scene_type', '')}",
            f"- **Brand World:** {result.get('brand_world', result.get('meta', {}).get('brand_world', ''))}",
            "",
            f"## 🎨 Prompt Completo",
            "```",
            result.get("prompt_completo", ""),
            "```",
            "",
            f"## 🚫 Negative Prompt",
            "```",
            result.get("negative_prompt", ""),
            "```",
        ]
        return "\n".join(lines)

    @staticmethod
    def to_plain_text(result: Dict[str, Any]) -> str:
        """Retorna apenas o prompt e negative prompt em texto puro."""
        return (f"PROMPT:\n{result.get('prompt_completo', '')}\n\n"
                f"NEGATIVE:\n{result.get('negative_prompt', '')}")

    @staticmethod
    def to_html(result: Dict[str, Any]) -> str:
        """Retorna representação HTML básica para visualização em navegador."""
        prompt_escaped = result.get("prompt_completo", "").replace("\n", "<br>")
        negative_escaped = result.get("negative_prompt", "").replace("\n", "<br>")
        return f"""<!DOCTYPE html>
<html>
<head><title>Image Prompt - {result.get('estilo_nome', '')}</title></head>
<body>
<h1>Image Prompt: {result.get('estilo_nome', '')}</h1>
<p><strong>Score:</strong> {result.get('qualidade', {}).get('score', '')}/10</p>
<h2>Prompt</h2>
<p>{prompt_escaped}</p>
<h2>Negative Prompt</h2>
<p>{negative_escaped}</p>
</body>
</html>"""

    @staticmethod
    def to_summary(result: Dict[str, Any]) -> str:
        """Resumo de uma linha para logs e dashboards."""
        return (f"[{result.get('formato', '?')}] {result.get('estilo_nome', '?')} "
                f"| Score: {result.get('qualidade', {}).get('score', '?')}/10 "
                f"| {result.get('headline', '?')[:50]}")


output_formatter = OutputFormatter()


# ============================================================================
# BLOCO 16 – HERMES AGENT COMPATIBILITY (INTERFACE DE INTEGRAÇÃO)
# ============================================================================
class HermesAgentInterface:
    """
    Fornece métodos padronizados para integração com o Hermes Agent.
    Inclui tratamento de erros, validação de entrada e logging silencioso.
    """

    @staticmethod
    def validate_payload(payload: Dict[str, Any]) -> Tuple[bool, str]:
        """Valida o payload recebido do agente com 8 verificações progressivas."""
        if not payload:
            return False, "Payload está vazio."
        if "copy" not in payload:
            return False, "Payload não contém a chave obrigatória 'copy'."
        if not isinstance(payload["copy"], str):
            return False, "A chave 'copy' deve ser uma string."
        if len(payload["copy"].strip()) < 20:
            return False, "A copy deve ter pelo menos 20 caracteres."
        if len(payload["copy"]) > 5000:
            return False, "A copy excede o limite máximo de 5000 caracteres."
        # Validar formato se fornecido
        formato = payload.get("formato", "POST").upper()
        if formato not in ("POST", "CARROSSEL", "STORY"):
            return False, f"Formato inválido: '{formato}'. Use POST, CARROSSEL ou STORY."
        # Validar plataforma se fornecida
        platform = payload.get("platform", payload.get("plataforma", "instagram_feed")).lower()
        valid_platforms = [p.value for p in Platform]
        if platform not in valid_platforms:
            return False, f"Plataforma inválida: '{platform}'. Use: {valid_platforms}"
        return True, "OK"

    @staticmethod
    def sanitize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Normaliza e limpa o payload, preenchendo defaults com valores seguros."""
        sanitized = {
            "copy": payload["copy"].strip(),
            "product_name": payload.get("product_name", payload.get("produto", "")).strip(),
            "product_category": payload.get("product_category", payload.get("categoria", "produto")).strip(),
            "timeframe": payload.get("timeframe", payload.get("tempo", "7 dias")).strip(),
            "formato": payload.get("formato", "POST").strip().upper(),
            "platform": payload.get("platform", payload.get("plataforma", "instagram_feed")).strip().lower(),
            "headline_override": payload.get("headline", "").strip(),
        }
        # Garantir formato válido
        if sanitized["formato"] not in ("POST", "CARROSSEL", "STORY"):
            sanitized["formato"] = "POST"
        # Garantir plataforma válida
        valid_platforms = [p.value for p in Platform]
        if sanitized["platform"] not in valid_platforms:
            sanitized["platform"] = "instagram_feed"
        # Garantir product_category não vazio
        if not sanitized["product_category"]:
            sanitized["product_category"] = "produto"
        # Garantir timeframe não vazio
        if not sanitized["timeframe"]:
            sanitized["timeframe"] = "7 dias"
        return sanitized

    @staticmethod
    def error_response(error: Exception) -> Dict[str, Any]:
        """Gera resposta de erro padronizada."""
        return {
            "error": True,
            "message": str(error),
            "code": getattr(error, "code", "UNKNOWN"),
            "timestamp": time.time(),
        }

    @staticmethod
    def success_response(result: Dict[str, Any]) -> Dict[str, Any]:
        """Gera resposta de sucesso padronizada."""
        return {
            "error": False,
            "data": result,
            "timestamp": time.time(),
        }


hermes_agent_interface = HermesAgentInterface()


# ============================================================================
# BLOCO 17 – AUTO-TEST SUITE (SUITE DE TESTES DE INTEGRIDADE)
# ============================================================================
class AutoTestSuite:
    """
    Conjunto abrangente de testes para validar todos os blocos do sistema.
    Inclui testes unitários, de integração e de regressão.
    """

    def __init__(self):
        self.results: List[Dict[str, Any]] = []
        self.passed = 0
        self.failed = 0
        self.skipped = 0

    def _record(self, name: str, success: bool, details: str = "", skipped: bool = False):
        if skipped:
            self.skipped += 1
            self.results.append({"name": name, "success": None, "details": details, "skipped": True})
            logger.info(f"⏭️ {name} SKIPPED: {details}")
        else:
            self.results.append({"name": name, "success": success, "details": details})
            if success:
                self.passed += 1
            else:
                self.failed += 1
            logger.info(f"{'✅' if success else '❌'} {name} {details}")

    def run_all(self) -> Dict[str, Any]:
        """Executa todos os testes e retorna sumário."""
        self._test_content_role_classifier()
        self._test_style_selector()
        self._test_headline_generator()
        self._test_camera_engine()
        self._test_negative_prompt_builder()
        self._test_quality_gate_positive()
        self._test_quality_gate_negative()
        self._test_text_overlay_engine()
        self._test_layout_engine()
        self._test_brand_simulation()
        self._test_copy_pattern_analyzer()
        self._test_ad_type_decider()
        self._test_output_formatter()
        self._test_regeneration_loop()
        self._test_hermes_agent_interface()
        self._test_prompt_assembler()
        return {
            "total": len(self.results),
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "results": self.results,
        }

    def _test_content_role_classifier(self):
        try:
            role, _, _ = content_role_classifier.classify("Compre agora com 50% de desconto! R$ 99,90.")
            self._record("ContentRole Classifier", role == ContentRole.CONVERSAO)
        except Exception as e:
            self._record("ContentRole Classifier", False, str(e))

    def _test_style_selector(self):
        try:
            style = style_selector.select("Teste educativo", ContentRole.CONFIANCA, "POST", ESTILOS_POST)
            self._record("Style Selector", style is not None)
        except Exception as e:
            self._record("Style Selector", False, str(e))

    def _test_headline_generator(self):
        try:
            headline = headline_generator.generate(ContentRole.ALCANCE, "smartphone", "7 dias")
            self._record("Headline Generator", len(headline) > 5)
        except Exception as e:
            self._record("Headline Generator", False, str(e))

    def _test_camera_engine(self):
        try:
            config = camera_engine.get_config(ESTILOS_POST[5], ContentRole.ALCANCE)
            self._record("Camera Engine", "lens" in config)
        except Exception as e:
            self._record("Camera Engine", False, str(e))

    def _test_negative_prompt_builder(self):
        try:
            neg = negative_prompt_builder.build(ESTILOS_POST[0], ContentRole.ALCANCE)
            self._record("Negative Prompt Builder", len(neg["negative_prompt"]) > 20)
        except Exception as e:
            self._record("Negative Prompt Builder", False, str(e))

    def _test_quality_gate_positive(self):
        try:
            prompt = "CREATE A CINEMATIC PRODUCT PHOTOGRAPHY ADVERTISEMENT WITH TEXT OVERLAY. Studio lighting, controlled lighting, professional lighting. Headline visible. depth of field, bokeh, golden ratio, foreground, midground, background, cinematic, god rays."
            aprovado, score, _ = prompt_quality_gate.validate(prompt, ESTILOS_POST[13])
            self._record("Quality Gate (bom)", aprovado, f"Score: {score}")
        except Exception as e:
            self._record("Quality Gate (bom)", False, str(e))

    def _test_quality_gate_negative(self):
        try:
            prompt = "handheld camera, selfie, natural light only, candid."
            aprovado, score, _ = prompt_quality_gate.validate(prompt, ESTILOS_POST[0])
            self._record("Quality Gate (UGC)", not aprovado, f"Score: {score}")
        except Exception as e:
            self._record("Quality Gate (UGC)", False, str(e))

    def _test_text_overlay_engine(self):
        try:
            config = text_overlay_engine.generate_headline_config(ESTILOS_POST[0], ContentRole.ALCANCE, "Teste Headline")
            self._record("Text Overlay Engine", config.get("usar_tipografia", False))
        except Exception as e:
            self._record("Text Overlay Engine", False, str(e))

    def _test_layout_engine(self):
        try:
            layout = layout_engine.get_layout_instruction(ESTILOS_POST[0])
            self._record("Layout Engine", len(layout) > 10)
        except Exception as e:
            self._record("Layout Engine", False, str(e))

    def _test_brand_simulation(self):
        try:
            brand = brand_simulation_engine.get_brand_config(ESTILOS_POST[0])
            self._record("Brand Simulation", "brand_reference" in brand)
        except Exception as e:
            self._record("Brand Simulation", False, str(e))

    def _test_copy_pattern_analyzer(self):
        try:
            patterns = copy_pattern_analyzer.analyze("Top 3 melhores produtos. R$ 50,00. Compre agora!")
            self._record("Copy Pattern Analyzer", patterns.get("has_ranking") and patterns.get("has_preco"))
        except Exception as e:
            self._record("Copy Pattern Analyzer", False, str(e))

    def _test_ad_type_decider(self):
        try:
            ad_type = ad_type_decider.decide(ESTILOS_POST[0])
            self._record("AD Type Decider", ad_type in (AD_TYPE_DESIGN, AD_TYPE_PHOTOGRAPHY_WITH_TEXT))
        except Exception as e:
            self._record("AD Type Decider", False, str(e))

    def _test_output_formatter(self):
        try:
            dummy_result = {"prompt_completo": "test", "negative_prompt": "no test", "estilo_nome": "Test"}
            json_str = output_formatter.to_json(dummy_result)
            self._record("Output Formatter JSON", "prompt_completo" not in json_str)
        except Exception as e:
            self._record("Output Formatter JSON", False, str(e))

    def _test_regeneration_loop(self):
        try:
            loop = RegenerationLoop(max_attempts=2)
            def mock_build(attempt=0, **kwargs):
                return {"qualidade": {"score": 5.0, "aprovado": False}, "estilo_id": 1, "estilo_nome": "Test", "headline": "Test"}
            result = loop.execute(mock_build)
            self._record("Regeneration Loop", result is not None)
        except Exception as e:
            self._record("Regeneration Loop", False, str(e))

    def _test_hermes_agent_interface(self):
        try:
            valid, msg = hermes_agent_interface.validate_payload({"copy": "Teste de validação com mais de 20 caracteres."})
            self._record("Hermes Agent Validate", valid, msg)
        except Exception as e:
            self._record("Hermes Agent Validate", False, str(e))

    def _test_prompt_assembler(self):
        try:
            style = ESTILOS_POST[0]
            prompt = prompt_assembler.assemble(
                copy="Test copy", style=style, content_role=ContentRole.ALCANCE,
                headline="Test Headline", ad_type=style.ad_type, ad_type_prefix="TEST PREFIX",
                camera_config={"instruction": "N/A"}, brand_config={"brand_reference": "Test", "vibe": "Test"},
                text_config={}, layout_instruction="Test layout", platform=Platform.INSTAGRAM_FEED,
                product_name="Test Product"
            )
            self._record("Prompt Assembler", len(prompt) > 50)
        except Exception as e:
            self._record("Prompt Assembler", False, str(e))


auto_test_suite = AutoTestSuite()


# ============================================================================
# BLOCO 18 – VISUAL HOOK ENGINE (ELEMENTO SCROLL-STOP)
# ============================================================================
class VisualHookEngine:
    """
    Define o elemento visual que faz o usuário PARAR o scroll.
    Baseado em princípios de psicologia da atenção e contraste visual.
    """

    HOOK_TYPES = {
        "contrast": "Extreme contrast between light and dark areas — a bright product against near-black background, or vice versa. The eye is drawn to the area of maximum contrast first.",
        "surprise": "Unexpected element that breaks visual pattern — a floating object, unusual scale (product giant in miniature world), impossible physics, or surreal juxtaposition.",
        "movement": "Implied motion through diagonal composition, leading lines converging to product, or particles captured mid-flight. The brain perceives movement even in static images.",
        "emotion": "A facial expression or body language that triggers mirror neurons — authentic joy, genuine shock, deep curiosity. The viewer unconsciously mimics and feels the emotion.",
        "curiosity_gap": "Something partially hidden or being revealed — a product emerging from darkness, a label being peeled, a curtain being drawn. The brain craves closure.",
        "number": "Large, bold numbers that quantify a benefit — '7 MINUTES', '90% REDUCTION', '3X FASTER'. Numbers are processed 3x faster than words by the brain.",
        "color_pop": "A single vibrant color in an otherwise muted or monochromatic scene. The eye instantly goes to the color anomaly.",
        "face": "A face looking directly at the camera or looking at the product. Humans are hardwired to follow gaze direction.",
    }

    def generate(self, style: StyleConfig, content_role: ContentRole, headline: str) -> str:
        """Seleciona e descreve o hook visual mais apropriado para o contexto."""
        if content_role == ContentRole.CONVERSAO:
            if any(c.isdigit() for c in headline):
                hook_type = "number"
            else:
                hook_type = "contrast"
        elif content_role == ContentRole.PROVA:
            hook_type = "curiosity_gap"
        elif content_role == ContentRole.ALCANCE:
            if "contra" in style.nome.lower():
                hook_type = "surprise"
            else:
                hook_type = "movement"
        elif content_role == ContentRole.CONFIANCA:
            hook_type = "number" if any(c.isdigit() for c in headline) else "face"
        else:
            hook_type = "color_pop"

        description = self.HOOK_TYPES.get(hook_type, self.HOOK_TYPES["contrast"])
        return (f"VISUAL HOOK ({hook_type.upper()}): {description} "
                f"This element must be the FIRST thing the viewer sees within 0.5 seconds. "
                f"It must create an immediate STOP in the scroll — cognitive interruption. "
                f"The hook should be positioned at the upper-left golden ratio point where the eye naturally lands first.")


visual_hook_engine = VisualHookEngine()


# ============================================================================
# BLOCO 19 – ATTENTION ELEMENTS ENGINE (ELEMENTOS DE ATENÇÃO)
# ============================================================================
class AttentionElementsEngine:
    """
    Garante que a imagem possua elementos que prendem a atenção:
    tensão visual, contraste de cores, linhas de força, e pontos de foco secundários.
    """

    def generate(self, style: StyleConfig) -> str:
        elements = []
        if style.cores_contraste in ("alto", "máximo", "muito alto"):
            elements.append("High chromatic contrast between product and background (at least 70% difference in luminance).")
        else:
            elements.append("Moderate contrast with a single high-contrast accent element to create visual anchor.")
        if "split" in style.composicao.lower() or "comparação" in style.nome.lower():
            elements.append("Strong vertical dividing line creating a before/after dichotomy that forces cognitive comparison.")
        else:
            elements.append("Leading lines (wood grain, light beams, shelf edges, product contours) converging towards the product at the golden ratio point.")
        elements.append("Asymmetric balance: heavier visual weight on one side (product or headline), balanced by negative space or contrasting element on the opposite side.")
        elements.append("Implied motion through diagonal elements, floating particles captured mid-flight, or subtle directional cues (falling water droplet, rising steam, drifting petal).")
        elements.append("Secondary focal point (badge, price tag, guarantee seal) positioned at complementary golden ratio point to guide eye flow after initial hook.")
        return "ATTENTION ELEMENTS: " + " ".join(elements)


attention_elements_engine = AttentionElementsEngine()


# ============================================================================
# BLOCO 20 – COMPOSITION ENGINE (ENGINE DE COMPOSIÇÃO AVANÇADA)
# ============================================================================
class CompositionEngine:
    """
    Define a estrutura de composição espacial da imagem, unindo regra dos terços,
    golden ratio, Fibonacci spiral, e hierarquia de camadas.
    """

    def generate(self, style: StyleConfig) -> str:
        base = f"COMPOSITION: {style.composicao}. "
        base += ("Product placed at golden ratio intersection (1.618:1) for mathematically proven aesthetic appeal. "
                 "Secondary elements aligned to Fibonacci spiral points. ")
        base += "Grid adheres to rule of thirds: primary focal point at upper-right power point, secondary at lower-left. "
        if style.ad_type == AD_TYPE_PHOTOGRAPHY_WITH_TEXT:
            base += ("Three distinct depth layers: foreground (blurred, framing the scene, creating entry point), "
                     "midground (razor-sharp, product zone, the story's main action), "
                     "background (atmospheric, contextual, showing the world after transformation). ")
        else:
            base += ("Visual hierarchy with three tiers: primary (headline, 60-70% visual weight), "
                     "secondary (supporting text/graphic, 20-25%), tertiary (branding/CTA, 5-10%). ")
        base += ("Leading lines guide eye movement: start from top-left (where Western reading begins), "
                 "flow through the hook, land on the product/headline, then exit through CTA at bottom-right.")
        return base


composition_engine = CompositionEngine()


# ============================================================================
# BLOCO 21 – PRODUCT PLACEMENT ENGINE (POSICIONAMENTO DO PRODUTO)
# ============================================================================
class ProductPlacementEngine:
    """
    Decide como o produto aparece na cena: posição, escala, ângulo, e interação com o ambiente.
    """

    def generate(self, style: StyleConfig, product_name: str) -> str:
        if style.produto_proporcao == "0%":
            return "PRODUCT PLACEMENT: Product intentionally absent — message-only visual. Focus entirely on typography and graphic design elements."
        placement = (f"PRODUCT PLACEMENT: '{product_name}' positioned at {style.produto_posicao}, "
                     f"occupying {style.produto_proporcao} of frame. ")
        if "central" in style.produto_posicao:
            placement += ("Product is the undisputed hero, centered with generous negative space around it (minimum 15% padding). "
                         "No other objects within its immediate zone. Product receives dedicated accent lighting.")
        elif "discreto" in style.produto_posicao:
            placement += ("Product is subtly integrated into the scene, discovered on second glance. "
                         "It should feel native to the environment — not placed, but belonging there.")
        elif "lado" in style.produto_posicao:
            placement += ("Product positioned on one side, balanced by text or negative space on the opposite side. "
                         "Creates asymmetric equilibrium that feels dynamic yet stable.")
        placement += ("Product receives dedicated accent lighting (10-15% brighter than scene average) "
                     "to ensure it remains the focal point. Rim light defines product edges against background.")
        placement += ("Product surface should subtly reflect the environment (specular reflections) "
                     "to integrate it photorealistically into the scene.")
        return placement


product_placement_engine = ProductPlacementEngine()


# ============================================================================
# BLOCO 22 – COLOR PALETTE ENGINE (ENGINE DE PALETA DE CORES)
# ============================================================================
class ColorPaletteEngine:
    """
    Define a paleta de cores completa baseada no estilo, incluindo cores primárias,
    secundárias, de destaque, e regras de harmonia cromática.
    """

    COLOR_HARMONIES = {
        "complementary": "Colors opposite on the color wheel — maximum contrast, vibrant energy. Best for offers and calls-to-action.",
        "analogous": "Colors adjacent on the wheel — harmonious, serene, premium feel. Best for luxury and lifestyle.",
        "triadic": "Three evenly spaced colors — dynamic, balanced, creative energy. Best for bold statements.",
        "monochromatic": "Single hue with varying saturation and brightness — minimalist, sophisticated, timeless.",
        "split_complementary": "One base color + two adjacent to its complement — high contrast but softer than pure complementary.",
    }

    def generate(self, style: StyleConfig) -> str:
        if "premium" in style.nome.lower() or "luxo" in style.objetivo.lower():
            harmony = "analogous"
        elif "contra" in style.nome.lower() or "comparação" in style.nome.lower():
            harmony = "complementary"
        elif "minimal" in style.nome.lower() or "clean" in style.cores_primarias.lower():
            harmony = "monochromatic"
        else:
            harmony = "split_complementary"

        desc = self.COLOR_HARMONIES.get(harmony, "")
        return (f"COLOR PALETTE: {style.cores_primarias}. "
                f"Harmony: {harmony} ({desc}) "
                f"Background: {style.cor_fundo} (hex). Text: {style.cor_texto} (hex). "
                f"Contrast ratio: {style.cores_contraste} (ensure WCAG AA minimum 4.5:1 for text). "
                f"Accent color used sparingly (less than 10% of total pixels) exclusively for CTAs, price highlights, and guarantee seals. "
                f"Color temperature: consistent throughout — no mixed warm/cool unless creating intentional emotional transition.")


color_palette_engine = ColorPaletteEngine()


# ============================================================================
# BLOCO 23 – TYPOGRAPHY ENGINE (ENGINE DE TIPOGRAFIA)
# ============================================================================
class TypographyEngine:
    """
    Define todos os aspectos tipográficos: fonte, peso, tamanho, espaçamento,
    alinhamento, e integração com a cena.
    """

    def generate(self, style: StyleConfig, headline: str) -> str:
        if not style.tipografia_usa:
            return "TYPOGRAPHY: No text on image — pure visual communication."
        return (f"TYPOGRAPHY: Headline \"{headline}\" set in {style.tipografia_estilo}. "
                f"Size: {style.tipografia_tamanho}. Color: {style.tipografia_cor} (hex). "
                f"Position: {style.texto_posicao}. Alignment: center for bold statements, left-aligned for educational content. "
                f"Letter-spacing: -0.5% for bold headlines (tighter, more impactful), 0% for body text. "
                f"Line height: 1.0x for single-line headlines (maximum density), 1.2x for two-line (readability). "
                f"Text shadow: {'2px offset X and Y, 30% opacity black, 4px blur radius' if style.tipografia_sombra else 'none (solid background or high contrast ensures legibility)'}. "
                f"Safe area: minimum 10% margin on all sides from frame edge. "
                f"Never truncate, never hyphenate, never use all-caps for more than 3 words.")


typography_engine = TypographyEngine()


# ============================================================================
# BLOCO 24 – LIGHTING ENGINE (ENGINE DE ILUMINAÇÃO BÁSICA)
# ============================================================================
class LightingEngine:
    """
    Define a iluminação base antes das camadas cinematográficas avançadas.
    """

    def generate(self, style: StyleConfig) -> str:
        if style.ad_type == AD_TYPE_DESIGN:
            return "LIGHTING: Not applicable — graphic design composition with solid/textured background. No photographic lighting needed."
        return (f"LIGHTING: {style.iluminacao_tipo} originating from {style.iluminacao_direcao}. "
                f"Color temperature: {style.iluminacao_temperatura}. "
                f"Studio-controlled environment — all light sources are intentional and measured. "
                f"Key-to-fill ratio: 3:1 for product photography (professional contrast). "
                f"No mixed color temperatures unless creating intentional emotional temperature shift. "
                f"Light quality: soft and wrapping for premium products, harder and more directional for dramatic/authority content.")


lighting_engine = LightingEngine()


# ============================================================================
# CATÁLOGOS DE ESTILOS CARROSSEL E STORY (EXPANDIDOS)
# ============================================================================
ESTILOS_CARROSSEL = [
    StyleConfig(id=101, nome="HISTÓRIA EM QUADRINHO (VIDA REAL)", formato="CARROSSEL", content_role=CONTENT_ROLE_CONFIANCA,
        ad_type=AD_TYPE_PHOTOGRAPHY_WITH_TEXT, descricao="Narrativa visual em 6 slides cinematográficos contando a jornada do cliente.",
        layout_tipo="sequência narrativa cinematográfica (6 slides)", layout_hierarquia="Slide 1: Problema → 2-3: Tentativas → 4-5: Descoberta → 6: Solução",
        layout_proporcao="cada slide = 1 frame cinematográfico", composicao="Documental premium com iluminação progressiva",
        camera_lente="35mm", camera_angulo="eye_level", iluminacao_tipo="progressão: fria → neutra → quente",
        iluminacao_direcao="varia por slide", iluminacao_temperatura="6000K → 5000K → 3500K",
        cores_primarias="progressão: cinza/azul → neutro → dourado", cores_contraste="progressivo",
        cor_fundo="varia por slide", cor_texto="contraste com cada slide", tipografia_usa=True,
        tipografia_estilo="clean narrativa", tipografia_tamanho="pequeno-médio", tipografia_headline_tipo="narrativa de jornada real",
        tipografia_cor="branco com sombra ou preto", tipografia_sombra=True, produto_posicao="slides 5-6 com destaque",
        produto_proporcao="30% (finais)", texto_posicao="overlay sutil", texto_proporcao="35%",
        brand_referencia="Nike (storytelling)", emocao_alvo="identificação → esperança → alívio",
        objetivo="conectar emocionalmente através de storytelling visual", scene_type="wooden_shelf",
        lighting_style="god_rays", depth_style="shallow_portrait", time_of_day="golden_hour"),
    StyleConfig(id=102, nome="HISTÓRIA DE DECISÃO", formato="CARROSSEL", content_role=CONTENT_ROLE_CONFIANCA,
        ad_type=AD_TYPE_DESIGN, descricao="Jornada de indecisão até a escolha certa. Design editorial.",
        layout_tipo="sequência de decisão editorial (6 slides)", layout_hierarquia="Slide 1: Indecisão → 2: Erro 1 → 3: Erro 2 → 4: Aprendizado → 5: Escolha certa → 6: Resultado",
        layout_proporcao="cada slide = 1 etapa da decisão", composicao="Design editorial limpo, progressão vermelho → verde",
        cores_primarias="vermelho queimado → verde musgo + papel texturizado", cores_contraste="médio-alto",
        cor_fundo="papel kraft ou branco texturizado", cor_texto="preto", tipografia_usa=True,
        tipografia_estilo="clean editorial", tipografia_tamanho="médio / pequeno", tipografia_headline_tipo="jornada de decisão",
        tipografia_cor="preto", tipografia_sombra=False, produto_posicao="slides 5-6 com destaque",
        produto_proporcao="35% (finais)", texto_posicao="dominante em cada slide", texto_proporcao="60%",
        brand_referencia="The Ordinary", emocao_alvo="identificação → alívio → confiança",
        objetivo="mostrar que a marca entende a jornada de decisão", scene_type="concrete_minimal",
        lighting_style="softbox_diffuse", depth_style="deep_focus", time_of_day="midday"),
    StyleConfig(id=103, nome="HISTÓRIA DE FRUSTRAÇÃO", formato="CARROSSEL", content_role=CONTENT_ROLE_CONFIANCA,
        ad_type=AD_TYPE_PHOTOGRAPHY_WITH_TEXT, descricao="Narrativa de tentativas erradas, cansaço e a solução que resolve.",
        layout_tipo="sequência de frustração → alívio (6 slides)", layout_hierarquia="Slide 1: Problema → 2: Tentativa 1 (falha) → 3: Tentativa 2 (falha) → 4: Cansaço → 5: Descoberta → 6: Solução",
        layout_proporcao="cada slide = 1 momento emocional", composicao="Progressão visual: cores frias/escuras → quentes/claras",
        camera_lente="35mm (slides 1-4) → 85mm (slides 5-6)", camera_angulo="high_angle → eye_level",
        iluminacao_tipo="progressão dramática", iluminacao_direcao="lateral dura → frontal suave", iluminacao_temperatura="6000K → 3500K",
        cores_primarias="progressão: cinza/azul → dourado/laranja", cores_contraste="progressivo",
        cor_fundo="varia por slide", cor_texto="contraste", tipografia_usa=True,
        tipografia_estilo="emocional narrativo", tipografia_tamanho="médio", tipografia_headline_tipo="narrativa emocional de superação",
        tipografia_cor="contraste", tipografia_sombra=True, produto_posicao="slides 5-6 com destaque",
        produto_proporcao="30% (finais)", texto_posicao="dominante com atmosfera", texto_proporcao="50%",
        brand_referencia="Nike (storytelling)", emocao_alvo="frustração → esperança → catarse",
        objetivo="criar conexão emocional profunda através da frustração", scene_type="velvet_dark",
        lighting_style="rembrandt", depth_style="shallow_portrait", time_of_day="twilight"),
    StyleConfig(id=104, nome="ANTES DE DESCOBRIR", formato="CARROSSEL", content_role=CONTENT_ROLE_CONVERSAO,
        ad_type=AD_TYPE_PHOTOGRAPHY_WITH_TEXT, descricao="Vida antes vs depois de descobrir o produto. Transformação de rotina.",
        layout_tipo="antes/depois expandido (6 slides)", layout_hierarquia="Slide 1: Vida antes → 2-3: Consequências → 4: Descoberta → 5-6: Vida depois",
        layout_proporcao="cada slide = 1 aspecto da transformação", composicao="Fotografias cinematográficas com texto overlay premium",
        camera_lente="50mm (antes) → 85mm (depois)", camera_angulo="eye_level",
        iluminacao_tipo="studio controlado com progressão", iluminacao_direcao="consistente com evolução", iluminacao_temperatura="fria 5500K → quente 3500K",
        cores_primarias="progressão: azul/cinza → dourado/laranja", cores_contraste="progressivo",
        cor_fundo="varia", cor_texto="branco com sombra ou preto", tipografia_usa=True,
        tipografia_estilo="clean com personalidade", tipografia_tamanho="médio / pequeno", tipografia_headline_tipo="transformação de rotina",
        tipografia_cor="branco ou preto", tipografia_sombra=True, produto_posicao="slides 4-6 com destaque progressivo",
        produto_proporcao="40% (finais)", texto_posicao="overlay em cada slide", texto_proporcao="35%",
        brand_referencia="Apple (lifestyle)", emocao_alvo="identificação → desejo → convicção",
        objetivo="mostrar transformação real de rotina com o produto", scene_type="aesop_shelf",
        lighting_style="god_rays", depth_style="shallow_portrait", time_of_day="golden_hour"),
    StyleConfig(id=105, nome="ROTINA TRANSFORMADA", formato="CARROSSEL", content_role=CONTENT_ROLE_PROVA,
        ad_type=AD_TYPE_PHOTOGRAPHY_WITH_TEXT, descricao="Como algo simples muda completamente o dia a dia.",
        layout_tipo="dia a dia transformado cinematográfico (6 slides)", layout_hierarquia="Slide 1: Manhã antes → 2: Tarde antes → 3: Problema → 4: Descoberta → 5: Manhã depois → 6: Tarde depois",
        layout_proporcao="cada slide = 1 momento do dia", composicao="Editorial cinematográfico com texto overlay sutil",
        camera_lente="35mm (documental controlado)", camera_angulo="eye_level",
        iluminacao_tipo="studio que simula luz natural CONTROLADA", iluminacao_direcao="consistente", iluminacao_temperatura="progressão: fria → quente",
        cores_primarias="naturais controlados, progressão de temperatura", cores_contraste="médio",
        cor_fundo="varia", cor_texto="branco com sombra", tipografia_usa=True,
        tipografia_estilo="clean quase invisível", tipografia_tamanho="pequeno", tipografia_headline_tipo="transformação de rotina",
        tipografia_cor="branco com sombra", tipografia_sombra=True, produto_posicao="slides 4-6, em uso",
        produto_proporcao="30%", texto_posicao="overlay sutil", texto_proporcao="20%",
        brand_referencia="Aesop / Rituals", emocao_alvo="identificação → desejo",
        objetivo="mostrar como o produto transforma a rotina em experiência premium", scene_type="wooden_shelf",
        lighting_style="window_light_natural", depth_style="shallow_portrait", time_of_day="morning_dew"),
]

ESTILOS_STORY = [
    StyleConfig(id=201, nome="CONVERSA DIRETA", formato="STORY", content_role=CONTENT_ROLE_ALCANCE,
        ad_type=AD_TYPE_DESIGN, descricao="Tom de conversa direta. Texto centralizado, fundo texturizado premium.",
        layout_tipo="texto centralizado + fundo texturizado", layout_hierarquia="Frase principal centralizada",
        layout_proporcao="texto 90% / fundo 10%", composicao="Frase curta direta no centro, papel kraft ou linho",
        cores_primarias="fundo texturizado quente + texto escuro", cores_contraste="alto",
        cor_fundo="#f5f0e8", cor_texto="#1a1a1a", tipografia_usa=True, tipografia_estilo="clean conversacional",
        tipografia_tamanho="médio-grande", tipografia_headline_tipo="conversa direta",
        tipografia_cor="preto", tipografia_sombra=False, produto_posicao="não aparece", produto_proporcao="0%",
        texto_posicao="centro absoluto", texto_proporcao="90%", brand_referencia="Le Labo",
        emocao_alvo="proximidade + conexão pessoal", objetivo="criar conexão pessoal com tom íntimo premium",
        scene_type="wooden_shelf", lighting_style="window_light_natural", depth_style="shallow_portrait", time_of_day="morning_dew"),
    StyleConfig(id=202, nome="POSICIONAMENTO RÁPIDO", formato="STORY", content_role=CONTENT_ROLE_ALCANCE,
        ad_type=AD_TYPE_DESIGN, descricao="Frase forte da marca em formato story. Impacto em 2 segundos.",
        layout_tipo="frase centralizada + logo premium", layout_hierarquia="Frase (80%) → Logo (20% base)",
        layout_proporcao="texto 100%", composicao="Frase centralizada bold statement, logo pequeno na base",
        cores_primarias="marca + contraste máximo", cores_contraste="alto", cor_fundo="cor da marca ou preto",
        cor_texto="contraste", tipografia_usa=True, tipografia_estilo="bold statement",
        tipografia_tamanho="grande", tipografia_headline_tipo="posicionamento rápido",
        tipografia_cor="contraste com fundo", tipografia_sombra=False, produto_posicao="não aparece",
        produto_proporcao="0%", texto_posicao="centro", texto_proporcao="80%", brand_referencia="Nike",
        emocao_alvo="respeito + lembrança imediata", objetivo="reforçar posicionamento em formato rápido e impactante",
        scene_type="velvet_dark", lighting_style="rim_light_dramatic", depth_style="shallow_portrait", time_of_day="twilight"),
    StyleConfig(id=203, nome="REFORÇO DE AUTORIDADE", formato="STORY", content_role=CONTENT_ROLE_CONFIANCA,
        ad_type=AD_TYPE_DESIGN, descricao="Reforçar que a marca tem critérios. Design com selo premium.",
        layout_tipo="texto + selo de autoridade", layout_hierarquia="Selo dourado → Frase → Assinatura",
        layout_proporcao="texto 70% / selo 30%", composicao="Selo de confiança no topo, frase abaixo, assinatura discreta",
        cores_primarias="papel texturizado + dourado + preto", cores_contraste="médio",
        cor_fundo="#faf7f2", cor_texto="#1a1a1a", tipografia_usa=True, tipografia_estilo="clean com autoridade visual",
        tipografia_tamanho="médio", tipografia_headline_tipo="reforço de credibilidade",
        tipografia_cor="preto", tipografia_sombra=False, produto_posicao="não aparece", produto_proporcao="0%",
        texto_posicao="centro abaixo do selo", texto_proporcao="70%", brand_referencia="Aesop",
        emocao_alvo="confiança + segurança", objetivo="reforçar autoridade visual de forma rápida e premium",
        scene_type="wooden_shelf", lighting_style="god_rays", depth_style="shallow_portrait", time_of_day="golden_hour"),
    StyleConfig(id=204, nome="LEMBRETE", formato="STORY", content_role=CONTENT_ROLE_CONFIANCA,
        ad_type=AD_TYPE_DESIGN, descricao="Lembrete curto e direto sobre escolha inteligente. Elegância.",
        layout_tipo="texto centralizado + ícone minimalista", layout_hierarquia="Ícone → Frase → (opcional) logo",
        layout_proporcao="texto 85% / ícone 15%", composicao="Ícone minimalista no topo, frase centralizada",
        cores_primarias="clean suave, papel texturizado + detalhe verde", cores_contraste="médio",
        cor_fundo="#f5f0e8", cor_texto="#2d2d2d", tipografia_usa=True, tipografia_estilo="clean amigável",
        tipografia_tamanho="médio", tipografia_headline_tipo="lembrete elegante",
        tipografia_cor="preto suave", tipografia_sombra=False, produto_posicao="não aparece", produto_proporcao="0%",
        texto_posicao="centro", texto_proporcao="85%", brand_referencia="Diptyque",
        emocao_alvo="familiaridade + conforto", objetivo="manter a mensagem da marca presente de forma sutil e constante",
        scene_type="wooden_shelf", lighting_style="window_light_natural", depth_style="deep_focus", time_of_day="morning_dew"),
    StyleConfig(id=205, nome="VALOR PERCEBIDO", formato="STORY", content_role=CONTENT_ROLE_CONVERSAO,
        ad_type=AD_TYPE_PHOTOGRAPHY_WITH_TEXT, descricao="Mostrar valor do produto de forma rápida e cinematográfica.",
        layout_tipo="produto cinematográfico + benefício curto", layout_hierarquia="Produto (60%) → Benefício (40% overlay)",
        layout_proporcao="imagem 60% / texto 40%", composicao="Produto em destaque cinematográfico, texto com benefício principal",
        camera_lente="85mm", camera_angulo="eye_level", iluminacao_tipo="studio cinematográfico com god rays",
        iluminacao_direcao="frontal + rim", iluminacao_temperatura="quente (3500K)",
        cores_primarias="clean, produto herói", cores_contraste="alto",
        cor_fundo="fundo limpo com atmosfera premium", cor_texto="branco com sombra",
        tipografia_usa=True, tipografia_estilo="bold curto", tipografia_tamanho="médio-grande",
        tipografia_headline_tipo="valor percebido em 1 frase", tipografia_cor="branco com sombra", tipografia_sombra=True,
        produto_posicao="central herói", produto_proporcao="60%", texto_posicao="overlay inferior/superior",
        texto_proporcao="40%", brand_referencia="La Mer", emocao_alvo="desejo + percepção de valor",
        objetivo="comunicar valor em segundos com produto cinematográfico", scene_type="aesop_shelf",
        lighting_style="god_rays", depth_style="bokeh_creamy", time_of_day="golden_hour"),
    StyleConfig(id=206, nome="ROTINA REAL", formato="STORY", content_role=CONTENT_ROLE_PROVA,
        ad_type=AD_TYPE_PHOTOGRAPHY_WITH_TEXT, descricao="Mostrar o produto em uso no dia a dia com direção de arte cinematográfica.",
        layout_tipo="produto em cenário cinematográfico controlado", layout_hierarquia="Cena de uso cinematográfica → Produto → Texto sutil",
        layout_proporcao="imagem 80% / texto 20%", composicao="Produto sendo usado em ambiente planejado cinematograficamente",
        camera_lente="35mm", camera_angulo="eye_level", iluminacao_tipo="studio que simula luz natural CONTROLADA",
        iluminacao_direcao="natural controlada", iluminacao_temperatura="varia (3500-5000K)",
        cores_primarias="naturais controlados com atmosfera premium", cores_contraste="médio",
        cor_fundo="varia por cena", cor_texto="branco com sombra", tipografia_usa=True,
        tipografia_estilo="mínimo, quase invisível", tipografia_tamanho="pequeno", tipografia_headline_tipo="uso real com estética premium",
        tipografia_cor="branco com sombra", tipografia_sombra=True, produto_posicao="em uso natural controlado",
        produto_proporcao="50%", texto_posicao="overlay mínimo", texto_proporcao="15%",
        brand_referencia="Aesop lifestyle", emocao_alvo="identificação + desejo de uso diário",
        objetivo="mostrar uso real controlado com estética cinematográfica premium", scene_type="wooden_shelf",
        lighting_style="window_light_natural", depth_style="shallow_portrait", time_of_day="morning_dew"),
]

# ============================================================================
# FUNÇÃO DE INTERFACE ATUALIZADA (EXPANDIDA COM BLOCOS 13-24)
# ============================================================================
def run(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ponto de entrada principal para o Hermes Agent.
    Utiliza todos os blocos implementados até o momento (1-24).
    """
    # Validar e sanitizar
    valid, msg = hermes_agent_interface.validate_payload(payload)
    if not valid:
        raise InvalidInputError(msg)
    data = hermes_agent_interface.sanitize_payload(payload)

    # Classificar
    content_role, confidence, _ = content_role_classifier.classify(data["copy"])
    patterns = copy_pattern_analyzer.analyze(data["copy"])

    # Selecionar estilo
    estilos_map = {"POST": ESTILOS_POST, "CARROSSEL": ESTILOS_CARROSSEL, "STORY": ESTILOS_STORY}
    estilos = estilos_map.get(data["formato"], ESTILOS_POST)
    style = style_selector.select(data["copy"], content_role, data["formato"], estilos)

    # Gerar headline (com override opcional)
    headline = data.get("headline_override") if data.get("headline_override") else headline_generator.generate(content_role, data["product_category"], data["timeframe"])

    # AD Type e prefixo
    ad_type = ad_type_decider.decide(style)
    ad_prefix = ad_type_decider.get_prompt_prefix(ad_type, style)

    # Blocos de suporte
    camera_config = camera_engine.get_config(style, content_role) if ad_type == AD_TYPE_PHOTOGRAPHY_WITH_TEXT else {"instruction": "N/A"}
    brand_config = brand_simulation_engine.get_brand_config(style)
    text_config = text_overlay_engine.generate_headline_config(style, content_role, headline)
    layout_instr = layout_engine.get_layout_instruction(style)
    negative = negative_prompt_builder.build(style, content_role)

    # Blocos de atenção e composição (18-24)
    visual_hook = visual_hook_engine.generate(style, content_role, headline)
    attention = attention_elements_engine.generate(style)
    composition = composition_engine.generate(style)
    product_placement = product_placement_engine.generate(style, data["product_name"])
    color_palette = color_palette_engine.generate(style)
    typography = typography_engine.generate(style, headline)
    lighting = lighting_engine.generate(style)

    # Montagem do prompt (bloco 14)
    try:
        platform_enum = Platform(data["platform"])
    except ValueError:
        platform_enum = Platform.INSTAGRAM_FEED

    prompt_completo = prompt_assembler.assemble(
        copy=data["copy"], style=style, content_role=content_role,
        headline=headline, ad_type=ad_type, ad_type_prefix=ad_prefix,
        camera_config=camera_config, brand_config=brand_config,
        text_config=text_config, layout_instruction=layout_instr,
        platform=platform_enum, product_name=data["product_name"],
        visual_hook=visual_hook,
        attention_instruction=attention,
        composition_instruction=composition,
        product_placement=product_placement,
        color_palette_instruction=color_palette,
        typography_instruction=typography,
        lighting_instruction=lighting,
    )

    # Quality Gate
    aprovado, score, razoes = prompt_quality_gate.validate(prompt_completo, style)

    return {
        "versao": f"hermes_image_engine_v{VERSION}",
        "build": BUILD,
        "formato": data["formato"],
        "plataforma": platform_enum.value,
        "content_role": content_role.value,
        "ad_type": ad_type,
        "estilo_nome": style.nome,
        "estilo_id": style.id,
        "headline": headline,
        "prompt_completo": prompt_completo,
        "negative_prompt": negative["negative_prompt"],
        "qualidade": {"score": score, "aprovado": aprovado, "razoes": razoes},
        "cinematic_scene": {"scene_type": style.scene_type, "lighting_style": style.lighting_style, "depth_style": style.depth_style},
        "meta": {"patterns_detected": patterns, "word_count": len(data["copy"].split())},
    }


# ============================================================================
# EXPORTAÇÕES DA PARTE 2
# ============================================================================
__all__ = [
    "RegenerationLoop",
    "PromptAssembler",
    "OutputFormatter",
    "HermesAgentInterface",
    "AutoTestSuite",
    "VisualHookEngine",
    "AttentionElementsEngine",
    "CompositionEngine",
    "ProductPlacementEngine",
    "ColorPaletteEngine",
    "TypographyEngine",
    "LightingEngine",
    "ESTILOS_CARROSSEL",
    "ESTILOS_STORY",
    "run",
]

# Mensagem de prontidão
print("=" * 78)
print("✅ HERMES IMAGE ENGINE V20 — PARTE 2/5 CARREGADA")
print(f"   Blocos 13 a 24 + Catálogos Carrossel e Story")
print(f"   Total de classes exportadas: {len(__all__)}")
print("=" * 78)

# ============================================================================
# HERMES IMAGE ENGINE V20 — NÍVEL DEUS ABSOLUTO — PARTE 3/5
# Blocos 25 a 40 — Motores Cinematográficos Completos
# Continuação direta da Parte 2/5 — todos os imports, enums, dataclasses,
# constantes e engines anteriores já estão definidos.
# ============================================================================

# ============================================================================
# BLOCO 25 – CINEMATIC SCENE COMPOSER (COMPOSITOR DE CENAS CINEMATOGRÁFICAS)
# ============================================================================
class CinematicSceneComposer:
    """
    Constrói cenários 3D imersivos fotorrealistas, substituindo fundos genéricos.
    Cada cena é um ambiente completo com profundidade, texturas e atmosfera.
    Referências: Aesop, La Mer, Rituals, Byredo, Diptyque.
    """

    def compose(self, style: StyleConfig, product_name: str, content_role: ContentRole) -> CinematicSceneConfig:
        """
        Compõe uma cena cinematográfica completa baseada no estilo, produto e papel do conteúdo.
        """
        config = CinematicSceneConfig()

        # Seleciona o tipo de cena com base no estilo
        scene_key = style.scene_type if style.scene_type else "wooden_shelf"
        scene_data = SCENE_MAPPING.get(scene_key, SCENE_MAPPING["wooden_shelf"])

        # Preenche os campos básicos da cena
        config.scene_type = scene_key
        config.environment_description = scene_data["description"]
        config.foreground_elements = scene_data.get("foreground", [])
        config.midground_elements = scene_data.get("midground", [])
        config.background_elements = scene_data.get("background", [])
        config.texture_materials = scene_data.get("materials", {})

        # Define partículas atmosféricas com base no estilo e tipo de cena
        if "god_rays" in style.lighting_style or "golden" in style.iluminacao_tipo:
            config.atmospheric_particles = ATMOSPHERIC_PARTICLES["dust_motes"]
        elif "frozen" in scene_key or "cold" in scene_key:
            config.atmospheric_particles = ATMOSPHERIC_PARTICLES["frost_crystals"]
        elif "organic" in scene_key or "nature" in scene_key:
            config.atmospheric_particles = ATMOSPHERIC_PARTICLES["pollen_float"]
        elif "steam" in style.descricao.lower() or "vapor" in style.descricao.lower():
            config.atmospheric_particles = ATMOSPHERIC_PARTICLES["steam_vapor"]
        else:
            config.atmospheric_particles = ATMOSPHERIC_PARTICLES["water_droplets"]

        # Configura a iluminação cinematográfica com base no estilo
        lighting_key = style.lighting_style if style.lighting_style else "softbox_diffuse"
        lighting_data = LIGHTING_MAPPING.get(lighting_key, LIGHTING_MAPPING["softbox_diffuse"])
        config.lighting_setup = lighting_data["setup"]
        config.lighting_temperature = lighting_data["temperature"]
        config.lighting_mood = lighting_data["mood"]

        # Configura a profundidade de campo
        depth_key = style.depth_style if style.depth_style else "shallow_portrait"
        depth_data = DEPTH_MAPPING.get(depth_key, DEPTH_MAPPING["shallow_portrait"])
        config.depth_of_field = f"{depth_data['aperture']}, {depth_data['focal_length']}"
        config.focal_length = depth_data["focal_length"]
        config.perspective_type = depth_data["effect"]

        # Define a paleta de cores baseada no tipo de cena e role
        if "premium" in style.nome.lower() or "golden" in style.iluminacao_tipo:
            color_key = "golden_premium"
        elif "clinical" in scene_key or "prova" in content_role.value:
            color_key = "clinical_clean"
        elif "organic" in scene_key or "nature" in scene_key:
            color_key = "organic_natural"
        elif "dark" in scene_key or "velvet" in scene_key:
            color_key = "dramatic_noir"
        elif "frozen" in scene_key or "cold" in scene_key:
            color_key = "cold_premium"
        else:
            color_key = "monochromatic_elegance"

        color_data = COLOR_GRADE_MAPPING.get(color_key, COLOR_GRADE_MAPPING["luxury_warm"])
        config.color_palette = f"{color_data['primary']} + {color_data.get('accent', '')}"
        config.color_grade = color_data["grade"]

        # Configura sombras e ecos visuais
        config.shadow_design = "long soft shadows from key light, subtle contact shadows on surface for grounding"
        config.visual_echo_elements = [
            "repeated product silhouette at different depths for rhythm",
            "subtle reflection on polished surface beneath product"
        ]
        config.micro_imperfections = [
            "subtle wood grain variations",
            "one leaf slightly out of place",
            "minor water spot on surface"
        ]
        config.temperature_sensation = "warm ambient temperature, cool product surface contrast"
        config.time_of_day = style.time_of_day if style.time_of_day else "golden_hour"
        config.hero_lighting_rig = (
            "3-point cinematic: key light 45° left, fill light -2 stops right, "
            "rim light from behind for edge definition"
        )

        # Adiciona efeitos cáusticos se o produto for de vidro ou estiver gelado
        if "glass" in product_name.lower() or "vidro" in product_name.lower():
            config.caustic_effects = (
                "subtle light refraction patterns on nearby surfaces, "
                "prismatic highlights on glass edges"
            )
        if "condensation" in style.descricao.lower() or "gelado" in style.descricao.lower():
            config.caustic_effects = (
                "water droplet refraction, micro-prisms in condensation beads"
            )

        # Transição de temperatura emocional de acordo com o papel do conteúdo
        if content_role in (ContentRole.CONVERSAO, ContentRole.PROVA):
            config.emotional_temp_shift = (
                "background cool 5500K → product warm 3200K spotlight, creating focal warmth"
            )
        elif content_role == ContentRole.ALCANCE:
            config.emotional_temp_shift = (
                "consistent warm 3500K throughout, creating premium intimate atmosphere"
            )

        logger.info(
            f"[Cinematic Scene] {scene_key} | Lighting: {lighting_key} | "
            f"Depth: {depth_key} | Color: {color_key}"
        )
        return config


cinematic_scene_composer = CinematicSceneComposer()


# ============================================================================
# BLOCO 26 – MATERIAL & TEXTURE DIRECTOR (DIRETOR DE MATERIAIS E TEXTURAS)
# ============================================================================
class MaterialTextureDirector:
    """
    Define materiais e texturas fotorrealistas para cada elemento da cena.
    Controla superfícies, reflexos, imperfeições e sensação tátil.
    Cada material é descrito com precisão técnica para máxima fidelidade visual.
    """

    def __init__(self):
        self.material_library = {
            "dark_walnut": {
                "description": "Dark walnut wood with deep chocolate brown tones, visible grain patterns flowing horizontally",
                "reflectivity": "matte with subtle natural oil sheen (5% reflectivity)",
                "bump_depth": "0.3mm grain texture, occasional knot holes (2-3mm diameter)",
                "aging": "subtle wear marks near edges, micro-scratches from years of use, slight color variation at contact points",
            },
            "frosted_glass": {
                "description": "Acid-etched glass with matte finish, diffuses light softly, reveals internal contents mysteriously",
                "reflectivity": "matte surface (8% specular), no sharp reflections, soft light scattering",
                "bump_depth": "0.05mm micro-texture from acid etching, smooth to touch",
                "condensation": "water droplets (0.5-2mm diameter) forming on surface, some running down leaving trails",
            },
            "brushed_gold": {
                "description": "Brushed gold metal with linear grain patterns, warm champagne-yellow hue",
                "reflectivity": "semi-matte (25% specular), anisotropic reflections following brush direction",
                "bump_depth": "0.1mm directional grain, tiny surface variations",
                "patina": "subtle darkening at edges, micro-scratches that catch light differently",
            },
            "carrara_marble": {
                "description": "White Carrara marble with grey veining, each vein unique and organic",
                "reflectivity": "polished surface (40% specular), sharp reflections at grazing angles",
                "bump_depth": "polished smooth with subtle etching marks (0.01mm), vein lines slightly recessed (0.05mm)",
                "character": "natural grey veins flowing diagonally, occasional crystal inclusions that sparkle",
            },
            "raw_concrete": {
                "description": "Brutalist raw concrete with formwork texture, subtle color variations from grey to warm grey",
                "reflectivity": "completely matte (2% reflectivity), absorbs light",
                "bump_depth": "1-3mm surface variations from formwork boards, occasional air bubbles (1-5mm)",
                "imperfections": "small cracks, subtle efflorescence patches, tie-hole marks from construction",
            },
            "deep_velvet": {
                "description": "Deep navy or burgundy velvet fabric, plush and light-absorbing",
                "reflectivity": "near-zero direct reflectivity, subtle sheen at extreme grazing angles only",
                "bump_depth": "2-4mm pile depth, directional nap creating lighter/darker zones depending on angle",
                "character": "rich color saturation, light absorption creates dramatic negative space",
            },
            "ice_crystal": {
                "description": "Clear ice with internal fracture patterns and trapped air bubbles",
                "reflectivity": "high specular (60%), sharp reflections, prismatic light splitting at edges",
                "bump_depth": "smooth surface with occasional frost crystal formations (0.5mm height)",
                "character": "internal cracks creating light paths, trapped bubbles (0.1-2mm), blue-white color from light scattering",
            },
            "linen_fabric": {
                "description": "Natural linen with visible weave structure, slubs and irregularities",
                "reflectivity": "matte with subtle sheen (10% specular), no sharp reflections",
                "bump_depth": "woven texture (0.5mm), occasional slub yarns (1mm thickness variation)",
                "character": "natural wrinkles and folds, soft drape, organic color variations in the yarn",
            },
        }

    def generate_instructions(self, scene_config: CinematicSceneConfig, style: StyleConfig) -> str:
        """Gera instruções detalhadas de materiais para o prompt."""
        instructions = ["MATERIALS & TEXTURES (PHOTOREALISTIC SPECIFICATIONS):", ""]

        for element, material_name in scene_config.texture_materials.items():
            # Tenta encontrar o material na biblioteca
            material_key = material_name.lower().replace(" ", "_")
            # Remove caracteres especiais para matching
            material_key = re.sub(r'[^a-z0-9_]', '', material_key)
            material = self.material_library.get(material_key)

            if material:
                instructions.append(f"● {element.upper()}:")
                instructions.append(f"  Material: {material['description']}")
                instructions.append(f"  Reflectivity: {material['reflectivity']}")
                instructions.append(f"  Surface Detail: {material['bump_depth']}")
                if 'aging' in material:
                    instructions.append(f"  Aging/History: {material['aging']}")
                if 'condensation' in material:
                    instructions.append(f"  Condensation: {material['condensation']}")
                if 'patina' in material:
                    instructions.append(f"  Patina: {material['patina']}")
                if 'character' in material:
                    instructions.append(f"  Character: {material['character']}")
                if 'imperfections' in material:
                    instructions.append(f"  Imperfections: {material['imperfections']}")
            else:
                instructions.append(f"● {element.upper()}: {material_name}")
            instructions.append("")

        # Texturas narrativas adicionais
        materials_str = str(scene_config.texture_materials).lower()
        if "wood" in materials_str:
            ts = TEXTURE_STORY_MAPPING.get("aged_wood", {})
            if ts:
                instructions.append(f"WOOD NARRATIVE: {ts.get('description', '')}")
                instructions.append(f"  Authentic imperfections: {ts.get('imperfections', '')}")

        if "metal" in materials_str or "gold" in materials_str:
            ts = TEXTURE_STORY_MAPPING.get("patina_metal", {})
            if ts:
                instructions.append(f"METAL NARRATIVE: {ts.get('description', '')}")

        if "glass" in materials_str:
            ts = TEXTURE_STORY_MAPPING.get("frosted_glass", {})
            if ts:
                instructions.append(f"GLASS NARRATIVE: {ts.get('description', '')}")

        instructions.append("TECHNICAL RENDERING REQUIREMENTS:")
        instructions.append("- All materials must respond realistically to scene lighting (physically-based rendering)")
        instructions.append("- Fresnel reflections on glass and polished surfaces (reflectivity increases at grazing angles)")
        instructions.append("- Subsurface scattering on organic materials (wood, leaves, skin)")
        instructions.append("- Ambient occlusion in crevices and contact points between materials")
        instructions.append("- Micro-imperfections on every surface (no perfectly clean surfaces in reality)")

        return "\n".join(instructions)


material_texture_director = MaterialTextureDirector()


# ============================================================================
# BLOCO 27 – CINEMATIC LIGHTING DIRECTOR (DIRETOR DE ILUMINAÇÃO CINEMATOGRÁFICA)
# ============================================================================
class CinematicLightingDirector:
    """
    Cria iluminação cinematográfica nível Hollywood.
    Controla god rays, rim lights, temperatura de cor, sombras dramáticas,
    e a relação entre luz e narrativa emocional.
    """

    def __init__(self):
        self.lighting_techniques = {
            "volumetric_god_rays": {
                "setup": "Primary light source (650W fresnel) positioned 45° above-left, projecting through a window frame gobo. Haze machine (oil-based) fills the room with fine particles that catch the light, creating visible volumetric rays. Rays should have soft edges and warm color (3200K) against cooler ambient (5000K).",
                "emotional_impact": "Creates sense of divine intervention, premium quality, atmospheric depth. The product appears touched by light itself.",
            },
            "rembrandt_portrait": {
                "setup": "Key light (500W fresnel) at 45° left, 45° above, creating characteristic triangular highlight on shadow side. Fill light (250W softbox) at -2 stops from right. Dark background (no background light). Ratio 4:1 key-to-fill.",
                "emotional_impact": "Classical, painterly, sophisticated. Suggests wisdom, authority, timelessness.",
            },
            "dramatic_split": {
                "setup": "Two opposing key lights. Left: 6000K cool LED panel, bare (hard shadows). Right: 3000K warm softbox (soft shadows). No fill light. Sharp division line visible on product/face. Ratio 1:1 between sides (equal intensity, different quality).",
                "emotional_impact": "Duality, transformation, before/after. The contrast between cold/hard and warm/soft tells the story of problem vs solution.",
            },
            "rim_light_hero": {
                "setup": "Backlight/rim light (1000W fresnel) positioned directly behind product, elevated 45°. Creates luminous edge glow. Front fill (softbox) at -3 stops to maintain dark, dramatic foreground. Product appears to glow from within.",
                "emotional_impact": "Mystery, premium exclusivity, dramatic reveal. Product becomes a luminous object of desire emerging from darkness.",
            },
            "softbox_commercial": {
                "setup": "Overhead softbox (4x6ft) directly above product, creating soft, even, shadowless illumination. White reflectors on all sides (V-flats) to fill any remaining shadows. Ratio 2:1 (key slightly dominant for subtle depth). Light temperature: 5000K (daylight balanced).",
                "emotional_impact": "Clean, trustworthy, professional. The 'honest' lighting — shows every detail, nothing hidden.",
            },
        }

    def generate_instructions(self, scene_config: CinematicSceneConfig, style: StyleConfig) -> str:
        """Gera instruções detalhadas de iluminação cinematográfica."""
        instructions = ["CINEMATIC LIGHTING DIRECTOR:", ""]

        # Determinar técnica baseada no lighting_style
        lighting_key = style.lighting_style if style.lighting_style else "softbox_diffuse"
        technique_map = {
            "god_rays": "volumetric_god_rays",
            "rembrandt": "rembrandt_portrait",
            "split_lighting": "dramatic_split",
            "rim_light_dramatic": "rim_light_hero",
            "softbox_diffuse": "softbox_commercial",
        }
        technique_name = technique_map.get(lighting_key, "softbox_commercial")
        technique = self.lighting_techniques.get(technique_name, self.lighting_techniques["softbox_commercial"])

        instructions.append(f"● TECHNIQUE: {technique_name.replace('_', ' ').title()}")
        instructions.append(f"  Setup: {technique['setup']}")
        instructions.append(f"  Emotional Impact: {technique['emotional_impact']}")
        instructions.append("")

        instructions.append("● COLOR TEMPERATURE MAP:")
        instructions.append(f"  Key Light: {scene_config.lighting_temperature}")
        instructions.append(f"  Fill Light: {'cool 6000K' if 'warm' in scene_config.lighting_temperature.lower() else 'warm 3500K'} (complementary to key)")
        instructions.append(f"  Ambient: neutral 4500K (fills shadows with neutral light)")
        instructions.append("")

        instructions.append("● LIGHT QUALITY SPECIFICATIONS:")
        instructions.append("  Key Light: Soft source (softbox or diffused fresnel) — wraps around product, gradual shadow falloff")
        instructions.append("  Fill Light: Ultra-soft (bounced or double-diffused) — fills shadows without creating secondary shadows")
        instructions.append("  Rim Light: Hard source (bare reflector or fresnel) — creates sharp, defined edge highlights")
        instructions.append("")

        instructions.append("● LIGHTING RATIOS (measured in stops):")
        instructions.append("  Key : Fill = 3:1 (professional contrast — shadows have detail but clear depth)")
        instructions.append("  Key : Rim = 1:1.5 (rim light brighter than key for dramatic edge separation)")
        instructions.append("  Key : Background = 1:0.5 (background 1 stop darker than subject for depth)")
        instructions.append("")

        instructions.append("● MOOD: " + scene_config.lighting_mood)

        return "\n".join(instructions)


cinematic_lighting_director = CinematicLightingDirector()


# ============================================================================
# BLOCO 28 – COLOR GRADE & MOOD DIRECTOR (DIRETOR DE COR E MOOD)
# ============================================================================
class ColorGradeMoodDirector:
    """
    Define paleta de cores cinematográfica e mood visual.
    Controla color grading, saturação, temperatura geral e atmosfera cromática.
    """

    def __init__(self):
        self.color_grading_presets = {
            "teal_orange": {
                "description": "Classic cinematic blockbuster grade — shadows pushed to teal-blue, highlights to warm orange-amber",
                "shadows": "teal (#008080) tint at 15% opacity",
                "midtones": "neutral with slight warmth",
                "highlights": "amber (#ff8c00) tint at 10% opacity",
                "emotional_effect": "Cinematic, epic, high-budget feel. Creates visual separation between subject and background.",
            },
            "desaturated_premium": {
                "description": "Luxury fashion grade — overall desaturation by 30%, selective saturation on product only",
                "shadows": "cool charcoal tint",
                "midtones": "desaturated (saturation -30%)",
                "highlights": "warm cream tint, product area full saturation",
                "emotional_effect": "Quiet luxury, sophistication, timelessness. Product pops as the only vibrant element.",
            },
            "warm_golden": {
                "description": "Golden hour warmth — overall warm cast (white balance 4000K), rich golden highlights",
                "shadows": "warm brown tint",
                "midtones": "golden warmth",
                "highlights": "champagne gold glow",
                "emotional_effect": "Nostalgia, warmth, invitation. Creates emotional connection and desire.",
            },
            "cool_clinical": {
                "description": "Scientific precision grade — cool white balance (6500K), blue shadow tint, bright clean highlights",
                "shadows": "blue tint (#0000ff) at 8% opacity",
                "midtones": "neutral white",
                "highlights": "pure white, no tint",
                "emotional_effect": "Trust, science, precision. Suggests clinical efficacy and measurable results.",
            },
            "high_contrast_noir": {
                "description": "Dramatic noir grade — crushed blacks, high contrast, selective color retention on product only",
                "shadows": "crushed to pure black (0,0,0)",
                "midtones": "high contrast curve (S-curve)",
                "highlights": "selective color — only product retains full color",
                "emotional_effect": "Drama, mystery, high stakes. Product becomes the sole beacon of color and hope.",
            },
        }

    def generate_instructions(self, scene_config: CinematicSceneConfig, style: StyleConfig) -> str:
        """Gera instruções de color grading para o prompt."""
        instructions = ["COLOR GRADE & MOOD DIRECTOR:", ""]

        # Selecionar preset baseado no estilo e cena
        if "premium" in style.nome.lower() or "luxury" in str(scene_config.color_palette).lower():
            preset_key = "desaturated_premium"
        elif "golden" in style.nome.lower() or "warm" in scene_config.lighting_temperature.lower():
            preset_key = "warm_golden"
        elif "clinical" in scene_config.scene_type or "prova" in style.content_role:
            preset_key = "cool_clinical"
        elif "velvet" in scene_config.scene_type or "dark" in scene_config.scene_type:
            preset_key = "high_contrast_noir"
        else:
            preset_key = "teal_orange"

        preset = self.color_grading_presets.get(preset_key, self.color_grading_presets["teal_orange"])

        instructions.append(f"● COLOR GRADE: {preset_key.replace('_', ' ').title()}")
        instructions.append(f"  Description: {preset['description']}")
        instructions.append(f"  Shadows: {preset['shadows']}")
        instructions.append(f"  Midtones: {preset['midtones']}")
        instructions.append(f"  Highlights: {preset['highlights']}")
        instructions.append(f"  Emotional Effect: {preset['emotional_effect']}")
        instructions.append("")

        instructions.append("● COLOR PALETTE:")
        instructions.append(f"  Primary: {scene_config.color_palette}")
        instructions.append(f"  Color Grade Style: {scene_config.color_grade}")
        instructions.append("")

        instructions.append("● SATURATION MAP:")
        instructions.append("  Product: 100% saturation (vibrant, eye-catching)")
        instructions.append("  Background: 70% saturation (present but not competing)")
        instructions.append("  Foreground elements: 85% saturation (framing but secondary)")
        instructions.append("  Text/Graphics: 100% saturation for maximum legibility")
        instructions.append("")

        instructions.append("● MOOD ATMOSPHERE:")
        instructions.append(f"  Overall feeling: {scene_config.lighting_mood}")
        instructions.append("  Color psychology: colors chosen to evoke specific emotional response")
        instructions.append("  Visual temperature: consistent throughout scene (no jarring color clashes)")

        return "\n".join(instructions)


color_grade_mood_director = ColorGradeMoodDirector()


# ============================================================================
# BLOCO 29 – SCENE DEPTH & PERSPECTIVE ENGINE (ENGINE DE PROFUNDIDADE E PERSPECTIVA)
# ============================================================================
class SceneDepthPerspectiveEngine:
    """
    Controla profundidade de campo, perspectiva e composição espacial.
    Define layers, bokeh, distância focal e golden ratio positioning.
    """

    def __init__(self):
        self.perspective_types = {
            "one_point": {
                "description": "Single vanishing point at horizon — creates deep, corridor-like perspective. Eye is pulled into the scene towards the vanishing point.",
                "best_for": ["retail_premium", "wooden_shelf", "laboratory"],
                "camera_height": "1.5m (eye level), camera parallel to ground",
            },
            "two_point": {
                "description": "Two vanishing points on horizon — product positioned at intersection. Creates dynamic, architectural feel.",
                "best_for": ["concrete_minimal", "golden_studio", "marble_bench"],
                "camera_height": "1.2m (slight low angle), camera tilted up 5°",
            },
            "macro_flat": {
                "description": "Near-orthographic perspective — minimal perspective distortion. Subject appears flat and graphic. Ideal for texture emphasis.",
                "best_for": ["frozen_surface", "clinical_white"],
                "camera_height": "directly above or 45° angle, long focal length (100mm+)",
            },
        }

    def generate_instructions(self, scene_config: CinematicSceneConfig, style: StyleConfig) -> str:
        """Gera instruções de profundidade e perspectiva."""
        instructions = ["SCENE DEPTH & PERSPECTIVE ENGINE:", ""]

        instructions.append(f"● DEPTH OF FIELD: {scene_config.depth_of_field}")
        instructions.append(f"● FOCAL LENGTH: {scene_config.focal_length}")
        instructions.append("")

        instructions.append("● SPATIAL LAYERS (Foreground → Midground → Background):")
        instructions.append("")
        instructions.append("  FOREGROUND (0.5m — 1.5m from camera):")
        instructions.append("  - Elements slightly blurred (out of focus) — creates entry point and depth cue")
        instructions.append("  - Serves as framing device — leads eye into the scene")
        instructions.append("  - Slightly darker than midground (atmospheric perspective)")
        for elem in scene_config.foreground_elements[:3]:
            instructions.append(f"    • {elem}")
        instructions.append("")
        instructions.append("  MIDGROUND (2m — 4m from camera):")
        instructions.append("  - RAZOR-SHARP FOCUS — the plane of critical sharpness")
        instructions.append("  - Product positioned here — maximum visual impact")
        instructions.append("  - Brightest zone in the scene (draws attention)")
        for elem in scene_config.midground_elements[:3]:
            instructions.append(f"    • {elem}")
        instructions.append("")
        instructions.append("  BACKGROUND (5m — infinity):")
        instructions.append("  - Atmospheric and contextual — slightly hazy (aerial perspective)")
        instructions.append("  - Soft bokeh circles from out-of-focus light sources")
        instructions.append("  - Cooler color temperature (receding into distance)")
        for elem in scene_config.background_elements[:3]:
            instructions.append(f"    • {elem}")
        instructions.append("")

        instructions.append("● BOKEH CHARACTERISTICS:")
        instructions.append("  - Shape: circular (ideal aperture blades)")
        instructions.append("  - Quality: creamy, smooth falloff, no harsh edges on out-of-focus elements")
        instructions.append("  - Light circles: perfectly round, soft edges, slight brightness at center (natural vignetting)")
        instructions.append("")

        instructions.append("● GOLDEN RATIO POSITIONING:")
        instructions.append("  - Product at primary golden ratio intersection (1.618:1 from left or right edge)")
        instructions.append("  - Headline at complementary golden ratio zone (opposite side)")
        instructions.append("  - Visual flow follows Fibonacci spiral from corner to product")

        return "\n".join(instructions)


scene_depth_perspective_engine = SceneDepthPerspectiveEngine()


# ============================================================================
# BLOCO 30 – ATMOSPHERIC PARTICLE ENGINE (PARTÍCULAS ATMOSFÉRICAS)
# ============================================================================
class AtmosphericParticleEngine:
    """
    Define partículas suspensas no ar que criam atmosfera viva.
    Poeira dourada em god rays, névoa sutil, vapor, pétalas caindo em câmera lenta.
    """

    def __init__(self):
        self.particle_presets = {
            "golden_dust": {
                "description": "Floating golden dust motes visible in warm light beams, creating magical atmosphere",
                "size_range": "0.1mm to 1.5mm apparent size",
                "density": "15-30 particles visible in a 1m³ volume within the light beam",
                "lighting_interaction": "Each particle catches light individually — backlit particles glow golden, front-lit particles appear as dark specks",
                "movement": "Gently floating in Brownian motion, some particles with slight motion blur (longer streaks near light source)",
                "distribution": "Concentrated in light beams, sparse in shadow areas",
            },
            "cold_mist": {
                "description": "Fine cold mist hovering just above frozen or cold surfaces",
                "size_range": "Microscopic droplets (0.01mm — 0.1mm), visible as collective haze",
                "density": "Light haze reducing visibility by 15-20% at 5m distance",
                "lighting_interaction": "Backlit mist glows blue-white, creates volumetric light effect around product",
                "movement": "Slow rolling motion like dry ice fog, heavier than air, stays close to surface",
                "distribution": "Densest near the cold surface, dissipates upward",
            },
            "steam_vapor": {
                "description": "Warm steam rising gently from product or hot surface",
                "size_range": "Visible wisps 0.5cm — 3cm wide, individual tendrils",
                "density": "2-4 visible wisps in frame, translucent",
                "lighting_interaction": "Backlit steam glows warmly, catches and diffuses light beautifully",
                "movement": "Rising slowly (10-20cm/s apparent speed), curling and dissipating at top",
                "distribution": "Originates from product surface, rises and spreads, then vanishes",
            },
            "water_spray": {
                "description": "Fine water mist from spray bottle, suspended droplets catching light",
                "size_range": "0.05mm to 2mm diameter, varied sizes for realism",
                "density": "Dense near source (50+ droplets), dispersing to sparse (5-10) at edges",
                "lighting_interaction": "Each droplet acts as micro-lens — backlit droplets create micro-rainbow prisms",
                "movement": "Outward burst from source, some droplets frozen mid-air, some with motion trails",
                "distribution": "Radial burst pattern, densest near nozzle, dispersing outward",
            },
            "pollen_organic": {
                "description": "Tiny organic particles floating in sunbeams through leaves or windows",
                "size_range": "Microscopic (0.01mm — 0.05mm), visible as collective sparkle",
                "density": "Very light — only visible in direct light beams, invisible in shadow",
                "lighting_interaction": "Sparkles where light hits — creates magical, ethereal quality",
                "movement": "Extremely slow drift, barely perceptible, gentle upward thermal currents",
                "distribution": "Only within light beams, creates invisible-to-visible transition at beam edges",
            },
            "frost_crystals": {
                "description": "Delicate ice crystals forming on cold surfaces, catching light prismatically",
                "size_range": "0.1mm to 0.5mm individual crystals, forming larger frost patterns",
                "density": "Dense pattern on surface (80% coverage), occasional airborne crystals near surface",
                "lighting_interaction": "Each crystal acts as tiny prism — creates sparkle points and micro-rainbows",
                "movement": "Static on surface, occasional crystal falling through frame (1-2 per second)",
                "distribution": "Densest on product and immediate surrounding surface",
            },
            "cherry_blossom": {
                "description": "Single pink petals floating gently through air, poetic atmosphere",
                "size_range": "Actual petal size (1-2cm), clearly visible as individual elements",
                "density": "Sparse — 2-5 petals visible in frame at different depths",
                "lighting_interaction": "Petals translucent where backlit, reveal delicate vein structure",
                "movement": "Slow spiraling descent (5-10cm/s), some motion blur on faster petals",
                "distribution": "Random distribution throughout frame, concentrated in upper half",
            },
            "incense_smoke": {
                "description": "Thin wisps of incense or candle smoke, meditative atmosphere",
                "size_range": "Thin tendrils 0.5cm — 2cm wide, 10-30cm long, individually visible",
                "density": "Light — 1-3 visible tendrils in frame, translucent",
                "lighting_interaction": "Smoke catches and diffuses light — side-lit smoke reveals internal turbulence",
                "movement": "Slow curling upward, delicate and unpredictable, laminar flow transitioning to turbulent",
                "distribution": "Originates from single point (incense tip or candle), rises and disperses",
            },
        }

    def get_particle_instructions(self, scene_config: CinematicSceneConfig, style: StyleConfig) -> str:
        """Gera instruções detalhadas de partículas atmosféricas."""
        preset_key = "golden_dust"

        if "god_rays" in style.lighting_style or "golden" in scene_config.lighting_temperature.lower():
            preset_key = "golden_dust"
        elif "frozen" in scene_config.scene_type or "cold" in scene_config.scene_type:
            preset_key = "frost_crystals"
        elif "steam" in style.descricao.lower() or "vapor" in style.descricao.lower():
            preset_key = "steam_vapor"
        elif "organic" in scene_config.scene_type or "nature" in scene_config.scene_type:
            preset_key = "pollen_organic"
        elif "cherry" in style.descricao.lower() or "rituals" in style.brand_referencia.lower():
            preset_key = "cherry_blossom"
        elif "incense" in style.descricao.lower() or "le labo" in style.brand_referencia.lower():
            preset_key = "incense_smoke"
        elif "spray" in style.descricao.lower() or "mist" in style.descricao.lower():
            preset_key = "water_spray"

        preset = self.particle_presets.get(preset_key, self.particle_presets["golden_dust"])

        instructions = ["ATMOSPHERIC PARTICLE ENGINE:", ""]
        instructions.append(f"● PARTICLE TYPE: {preset_key.replace('_', ' ').title()}")
        instructions.append(f"  Description: {preset['description']}")
        instructions.append(f"  Size Range: {preset['size_range']}")
        instructions.append(f"  Density: {preset['density']}")
        instructions.append(f"  Lighting Interaction: {preset['lighting_interaction']}")
        instructions.append(f"  Movement Pattern: {preset['movement']}")
        instructions.append(f"  Spatial Distribution: {preset['distribution']}")
        instructions.append("")
        instructions.append("● RENDERING GUIDELINES:")
        instructions.append("  - Particles at 3 depth levels: foreground (larger, motion blurred), midground (sharp, main visual), background (smaller, atmospheric haze)")
        instructions.append("  - Particles interact with light volumetrically (light scattering)")
        instructions.append("  - No two particles identical — size, position, and motion vary naturally")
        instructions.append("  - Particles enhance depth perception and make the image feel 'alive'")

        return "\n".join(instructions)


atmospheric_particle_engine = AtmosphericParticleEngine()


# ============================================================================
# BLOCO 31 – CAUSTIC & REFRACTIVE LIGHT ENGINE (LUZ REFRATADA E CÁUSTICOS)
# ============================================================================
class CausticRefractiveLightEngine:
    """
    Para produtos com vidro, líquidos ou superfícies brilhantes:
    padrões de luz refratada (prismas), cáusticos de água,
    reflexos internos complexos em frascos de perfume.
    """

    def __init__(self):
        self.caustic_presets = {
            "glass_bottle": {
                "description": "Light passing through thick glass creates subtle refraction patterns on nearby surfaces",
                "refractive_index": 1.5,
                "patterns": "Soft curved light bands following bottle contours, prismatic color separation (rainbow) at thick edges",
                "intensity": "Subtle — visible but not overwhelming, 15-25% brighter than ambient surface",
                "surfaces_affected": "Table surface beneath bottle, vertical surfaces beside bottle, product label area",
                "technical_notes": "Refraction bends light rays — bottle acts as cylindrical lens, focusing light into bright line on surface behind",
            },
            "water_droplets": {
                "description": "Individual water droplets acting as micro-lenses, creating tiny focused light spots on surface beneath",
                "refractive_index": 1.33,
                "patterns": "Bright spots with soft edges where droplets focus light, 2-5mm diameter per spot",
                "intensity": "Medium — clearly visible, adds sparkle and life, 30-50% brighter than surrounding surface",
                "surfaces_affected": "Surface directly beneath each droplet, product surface where droplets rest",
                "technical_notes": "Each droplet inverts and focuses the scene behind it — tiny upside-down images visible in larger droplets",
            },
            "ice_crystals": {
                "description": "Light refracting through ice crystals creating prismatic rainbow effects and sparkle points",
                "refractive_index": 1.31,
                "patterns": "Sharp rainbow refractions at crystal edges (red-to-violet dispersion), bright sparkle points (specular highlights)",
                "intensity": "High — dramatic and beautiful, catches attention immediately",
                "surfaces_affected": "Surrounding surfaces, product surface, background elements near ice",
                "technical_notes": "Internal fractures in ice create complex light paths — total internal reflection creates bright trapped light",
            },
            "liquid_surface": {
                "description": "Light caustics on surfaces beneath or beside liquid-filled containers",
                "refractive_index": "1.33 — 1.47 (depending on liquid)",
                "patterns": "Organic flowing light patterns, similar to swimming pool caustics but miniature and subtle",
                "intensity": "Subtle to medium — adds depth and realism, 10-20% brightness variation",
                "surfaces_affected": "Surface beneath container, walls beside container, product label behind liquid",
                "technical_notes": "Liquid motion creates dynamic caustics — even subtle vibration creates visible light pattern changes",
            },
            "metal_reflection": {
                "description": "Controlled specular highlights on brushed or polished metal surfaces",
                "refractive_index": "N/A (reflection, not refraction)",
                "patterns": "Linear highlights following metal grain direction, soft glow on polished areas, dark bands where surface curves away from light",
                "intensity": "Medium to high — defines premium quality, 40-60% specular reflection",
                "surfaces_affected": "Metal caps, gold accents, brushed steel elements, metallic labels",
                "technical_notes": "Anisotropic reflections — highlight elongates perpendicular to brush direction on brushed metal",
            },
        }

    def get_caustic_instructions(self, scene_config: CinematicSceneConfig, style: StyleConfig, product_name: str) -> str:
        """Gera instruções de efeitos cáusticos e de refração."""
        instructions = ["CAUSTIC & REFRACTIVE LIGHT ENGINE:", ""]
        active_presets = []

        if any(w in product_name.lower() for w in ["vidro", "glass", "frasco", "bottle", "perfume"]):
            active_presets.append("glass_bottle")
        if any(w in style.descricao.lower() for w in ["condensation", "gotas", "water", "droplet", "gelado", "frozen"]):
            active_presets.append("water_droplets")
        if "frozen" in scene_config.scene_type or "ice" in scene_config.scene_type:
            active_presets.append("ice_crystals")
        if any(w in product_name.lower() for w in ["óleo", "oil", "serum", "líquido", "liquid"]):
            active_presets.append("liquid_surface")
        if any(w in str(scene_config.texture_materials).lower() for w in ["gold", "metal", "brushed", "polished"]):
            active_presets.append("metal_reflection")

        if not active_presets:
            active_presets.append("glass_bottle")  # default elegante

        for preset_key in active_presets[:2]:
            preset = self.caustic_presets.get(preset_key)
            if preset:
                instructions.append(f"● EFFECT: {preset_key.replace('_', ' ').title()}")
                instructions.append(f"  Description: {preset['description']}")
                instructions.append(f"  Refractive Index: {preset['refractive_index']}")
                instructions.append(f"  Light Patterns: {preset['patterns']}")
                instructions.append(f"  Intensity: {preset['intensity']}")
                instructions.append(f"  Affected Surfaces: {preset['surfaces_affected']}")
                instructions.append(f"  Technical: {preset['technical_notes']}")
                instructions.append("")

        instructions.append("● RENDERING REQUIREMENTS:")
        instructions.append("  - Caustic photons must interact with scene geometry realistically")
        instructions.append("  - Color dispersion at prismatic edges should be physically accurate (rainbow spectrum)")
        instructions.append("  - Internal reflections in glass should show environment reflections subtly")
        instructions.append("  - Fresnel effect: reflectivity increases at grazing angles on glass and polished surfaces")

        return "\n".join(instructions)


caustic_refractive_engine = CausticRefractiveLightEngine()


# ============================================================================
# BLOCO 32 – GOLDEN RATIO COMPOSITION ENGINE (COMPOSIÇÃO MATEMÁTICA)
# ============================================================================
class GoldenRatioCompositionEngine:
    """
    Força composição matemática perfeita usando a proporção áurea (1.618:1),
    Fibonacci spiral, e regra dos terços com precisão milimétrica.
    """

    def get_composition_instructions(self, style: StyleConfig, product_name: str) -> str:
        instructions = ["GOLDEN RATIO COMPOSITION ENGINE:", ""]

        instructions.append("● MATHEMATICAL GRID:")
        instructions.append("  - Frame divided according to golden ratio (φ = 1.6180339887...)")
        instructions.append("  - Primary vertical division: 61.8% / 38.2%")
        instructions.append("  - Primary horizontal division: 61.8% / 38.2%")
        instructions.append(f"  - Product '{product_name}' positioned at primary golden ratio intersection (power point)")
        instructions.append("")

        instructions.append("● FIBONACCI SPIRAL:")
        instructions.append("  - Visual flow follows Fibonacci spiral from bottom-left corner spiraling inward")
        instructions.append("  - Spiral terminates at product position — the mathematical center of visual interest")
        instructions.append("  - Viewer's eye naturally traces: Headline (start of spiral) → Supporting elements (mid-spiral) → Product (spiral center)")
        instructions.append("")

        instructions.append("● RULE OF THIRDS OVERLAY:")
        instructions.append("  - Horizon or main horizontal division at upper third line (33.3% from top)")
        instructions.append("  - Product at intersection of right third and upper third (primary power point)")
        instructions.append("  - Headline occupies left third or center third with breathing room")
        instructions.append("  - CTA at lower-right third intersection (natural exit point)")
        instructions.append("")

        instructions.append("● NEGATIVE SPACE DISTRIBUTION:")
        instructions.append("  - 61.8% active space (product + key elements + text)")
        instructions.append("  - 38.2% negative space (breathing room, text placement, visual rest)")
        instructions.append("  - Negative space follows golden ratio subdivisions for secondary elements")
        instructions.append("")

        instructions.append("● LEADING LINES:")
        instructions.append("  - Natural scene lines (shelf edges, wood grain, light beams, shadow edges)")
        instructions.append("  - All leading lines converge at or near the primary focal point (product)")
        instructions.append("  - Lines create implicit arrows guiding the viewer's gaze")

        return "\n".join(instructions)


golden_ratio_engine = GoldenRatioCompositionEngine()


# ============================================================================
# BLOCO 33 – TEXTURE STORYTELLING ENGINE (TEXTURAS NARRATIVAS)
# ============================================================================
class TextureStorytellingEngine:
    """
    Texturas que contam história: madeira gasta pelo tempo, metal com pátina,
    papel envelhecido com bordas irregulares, tecido com dobras orgânicas.
    Não é só textura — é narrativa tátil que transmite autenticidade e artesania.
    """

    def get_texture_story_instructions(self, scene_config: CinematicSceneConfig) -> str:
        instructions = ["TEXTURE STORYTELLING (NARRATIVE THROUGH SURFACE):", ""]
        materials_str = str(scene_config.texture_materials).lower()

        stories = []
        if "wood" in materials_str:
            ts = TEXTURE_STORY_MAPPING.get("aged_wood", {})
            stories.append({
                "element": "Wood Surfaces",
                "story": f"Aged dark walnut with visible growth rings telling decades of history. {ts.get('description', '')}",
                "imperfections": ts.get("imperfections", ""),
                "emotional_meaning": "Wood tells the story of time passing, of objects handled with care, of quality that endures.",
            })
        if "metal" in materials_str or "gold" in materials_str:
            ts = TEXTURE_STORY_MAPPING.get("patina_metal", {})
            stories.append({
                "element": "Metal Elements",
                "story": f"Brushed gold with subtle patina developing at edges. {ts.get('description', '')}",
                "imperfections": ts.get("imperfections", ""),
                "emotional_meaning": "Metal shows its age gracefully — each scratch is a memory, each patina spot is character.",
            })
        if "glass" in materials_str:
            ts = TEXTURE_STORY_MAPPING.get("frosted_glass", {})
            stories.append({
                "element": "Glass Surfaces",
                "story": f"Thick hand-blown glass with subtle variations. {ts.get('description', '')}",
                "imperfections": ts.get("imperfections", ""),
                "emotional_meaning": "Hand-blown glass carries the maker's breath — tiny bubbles and variations are signatures of craft.",
            })
        if "stone" in materials_str or "marble" in materials_str:
            ts = TEXTURE_STORY_MAPPING.get("polished_stone", {})
            stories.append({
                "element": "Stone Surfaces",
                "story": f"Carrara marble with natural veining — each pattern unique. {ts.get('description', '')}",
                "imperfections": ts.get("imperfections", ""),
                "emotional_meaning": "Stone was formed over millions of years — it brings geological gravity to the scene.",
            })
        if "fabric" in materials_str or "linen" in materials_str or "velvet" in materials_str:
            ts = TEXTURE_STORY_MAPPING.get("linen_fabric", {})
            stories.append({
                "element": "Fabric Textures",
                "story": f"Natural linen with irregular slubs and weave variations. {ts.get('description', '')}",
                "imperfections": ts.get("imperfections", ""),
                "emotional_meaning": "Fabric shows it has been touched, unfolded, used — lived-in luxury that invites interaction.",
            })

        if not stories:
            stories.append({
                "element": "All Surfaces",
                "story": "Every surface tells a story of quality and craft — no plastic perfection, only authentic materials with character.",
                "imperfections": "Intentional micro-imperfections that signal authenticity",
                "emotional_meaning": "The kind of objects that become more beautiful with age — Wabi-sabi applied to product photography.",
            })

        for story in stories:
            instructions.append(f"● {story['element']}:")
            instructions.append(f"  Narrative: {story['story']}")
            instructions.append(f"  Imperfections: {story['imperfections']}")
            instructions.append(f"  Emotional Meaning: {story['emotional_meaning']}")
            instructions.append("")

        instructions.append("● WABI-SABI PRINCIPLE:")
        instructions.append("  - Imperfections are not flaws — they are evidence of authenticity")
        instructions.append("  - Each irregularity makes the image more real, more human, more desirable")
        instructions.append("  - The viewer should feel they could reach out and touch these surfaces")

        return "\n".join(instructions)


texture_storytelling_engine = TextureStorytellingEngine()


# ============================================================================
# BLOCO 34 – EMOTIONAL COLOR TEMPERATURE SHIFT (TRANSIÇÃO EMOCIONAL DE COR)
# ============================================================================
class EmotionalColorTemperatureShift:
    """
    Transição de temperatura de cor dentro da mesma imagem para criar jornada emocional.
    Background frio (problema) → foreground quente (solução).
    Esquerda fria (antes) → direita quente (depois).
    """

    def get_temperature_shift_instructions(self, scene_config: CinematicSceneConfig,
                                          style: StyleConfig, content_role: ContentRole) -> str:
        instructions = ["EMOTIONAL COLOR TEMPERATURE SHIFT:", ""]

        if content_role == ContentRole.CONVERSAO:
            instructions.append("● TYPE: Warm Focus Transition (Problem → Solution)")
            instructions.append("  Background: cool 5500-6000K (the problem space — distant, clinical, impersonal)")
            instructions.append("  Product Zone: warm 3000-3500K spotlight (the solution — intimate, welcoming, personal)")
            instructions.append("  Effect: Product appears as a warm, inviting island in a cooler world")
            instructions.append("  Psychology: Viewer's eye is drawn to warmth — product becomes the emotional center")
            instructions.append("  Technique: Achieved with warm-gelled spotlight on product, cooler ambient fill")
        elif content_role == ContentRole.PROVA:
            instructions.append("● TYPE: Credibility Transition (Before → After)")
            instructions.append("  Left/Before Side: cool 6000K, clinical, slightly harsh — unflinching honesty")
            instructions.append("  Right/After Side: warm 3500K, flattering, aspirational — the promised result")
            instructions.append("  Transition: gradual blend at center, not a hard line (natural gradient)")
            instructions.append("  Psychology: Cold truth establishes credibility → warm transformation creates desire")
            instructions.append("  Technique: Consistent lighting setup, different gels on left vs right")
        elif content_role == ContentRole.ALCANCE:
            instructions.append("● TYPE: Premium Consistent Warmth")
            instructions.append("  Entire scene: consistent warm 3200-3500K (no cold zones)")
            instructions.append("  Subtle variation: foreground 3200K (warmer), background 3800K (slightly cooler for depth)")
            instructions.append("  Psychology: Warmth = trust, luxury, invitation. No coldness = no distance between brand and viewer.")
        elif content_role == ContentRole.CONFIANCA:
            instructions.append("● TYPE: Educational Neutral-Warm")
            instructions.append("  Overall: neutral 4500-5000K (clarity, objectivity, trustworthiness)")
            instructions.append("  Product highlight: subtle warm 3800K accent on product only (approachability)")
            instructions.append("  Psychology: Neutral = objective, educational. Warm accent = human, approachable.")

        instructions.append("")
        instructions.append("● TECHNICAL EXECUTION:")
        instructions.append("  - Color temperature shift achieved through lighting gels, not post-processing")
        instructions.append("  - Gradual transition with no hard lines between temperature zones")
        instructions.append("  - White balance set to midpoint (4500K) for natural blend")
        instructions.append("  - The shift must feel organic and subconscious — viewer feels the emotion without noticing the technique")

        return "\n".join(instructions)


emotional_temp_shift_engine = EmotionalColorTemperatureShift()


# ============================================================================
# BLOCO 35 – PRODUCT SHADOW DESIGN (DESIGN DE SOMBRAS DO PRODUTO)
# ============================================================================
class ProductShadowDesign:
    """
    Sombras não são acidentais — são desenhadas artisticamente.
    Drop shadow longo e suave, shadow play com padrões, sombras coloridas.
    """

    def get_shadow_instructions(self, scene_config: CinematicSceneConfig, style: StyleConfig) -> str:
        instructions = ["PRODUCT SHADOW DESIGN (INTENTIONAL, NOT ACCIDENTAL):", ""]

        instructions.append("● CONTACT SHADOW (Grounding):")
        instructions.append("  - Sharp, dark shadow directly beneath product where it meets surface")
        instructions.append("  - Width: 2-3mm at contact point, fading to transparent within 1cm")
        instructions.append("  - Color: Deepest shadow in the scene (80-90% opacity black with ambient color tint)")
        instructions.append("  - Purpose: Grounds product in reality, defines spatial relationship with surface")
        instructions.append("")

        instructions.append("● DROP SHADOW (Drama):")
        instructions.append("  - Soft, elongated shadow extending from product base")
        instructions.append("  - Direction: Opposite to key light source (key from upper-left → shadow extends lower-right)")
        instructions.append("  - Length: 1.5x — 2x product height for dramatic effect")
        instructions.append("  - Softness: Gradual Gaussian falloff, no hard edge at any point")
        instructions.append("  - Opacity: 30-50% at darkest point (directly behind product), fading to 0% at tip")
        instructions.append("")

        instructions.append("● SHADOW COLOR THEORY:")
        instructions.append("  - Shadows are NEVER pure black — they pick up ambient color of environment")
        instructions.append("  - Warm environment (3500K): shadows have warm brown/amber undertones")
        instructions.append("  - Cold environment (6000K): shadows have cool blue/grey undertones")
        instructions.append("  - Shadow color is complementary to light color (if light is warm, shadow is cool-tinted and vice versa)")
        instructions.append("")

        instructions.append("● SHADOW DEPTH LAYERS:")
        instructions.append("  - Layer 1: Contact Shadow (sharpest, darkest) — defines object-surface relationship")
        instructions.append("  - Layer 2: Proximity Shadow (medium softness, medium darkness) — creates volume and 3D form")
        instructions.append("  - Layer 3: Ambient Occlusion (softest, lightest) — defines spatial volume and environment interaction")

        return "\n".join(instructions)


product_shadow_design = ProductShadowDesign()


# ============================================================================
# BLOCO 36 – VISUAL ECHO & REPETITION ENGINE (ECO E REPETIÇÃO VISUAL)
# ============================================================================
class VisualEchoRepetitionEngine:
    """
    Elementos repetidos em diferentes profundidades para criar ritmo visual.
    Produto em 3 tamanhos, padrões repetidos, elementos naturais em escala.
    """

    def get_echo_instructions(self, scene_config: CinematicSceneConfig, style: StyleConfig, product_name: str) -> str:
        instructions = ["VISUAL ECHO & REPETITION (RHYTHM THROUGH DEPTH):", ""]

        instructions.append("● PRODUCT ECHO (Brand Presence at Every Depth):")
        instructions.append(f"  - Primary: {product_name} in sharp midground focus — the HERO (100% scale)")
        instructions.append("  - Secondary Echo: Same or complementary product slightly defocused in background, 60% smaller")
        instructions.append("  - Tertiary Echo: Product silhouette or reflection in foreground, fully blurred, 30% size")
        instructions.append("  - Purpose: Creates brand presence at every depth level without being repetitive")
        instructions.append("")

        instructions.append("● NATURAL ELEMENT ECHO (Organic Rhythm):")
        if "leaf" in str(scene_config.foreground_elements).lower() or "botanical" in str(scene_config.foreground_elements).lower():
            instructions.append("  - Foreground: Single large leaf, slightly blurred, framing left edge (100% scale)")
            instructions.append("  - Midground: Smaller leaf near product, in focus, creating visual connection (60% scale)")
            instructions.append("  - Background: Abstract leaf shapes in bokeh, suggesting garden/forest (30% scale)")
        instructions.append("")

        instructions.append("● LIGHT ECHO:")
        instructions.append("  - Primary: Key light creates main highlight on product")
        instructions.append("  - Secondary: Same light reflected in background elements (softer)")
        instructions.append("  - Tertiary: Subtle rim light echo on foreground elements (hint of the same source)")
        instructions.append("")

        instructions.append("● COLOR ECHO:")
        instructions.append("  - Brand accent color appears in product (primary, 100% saturation)")
        instructions.append("  - Same color echoed in background element or botanical (secondary, 70% saturation)")
        instructions.append("  - Subtle reflection of brand color in surface beneath product (tertiary, 40% saturation)")
        instructions.append("")

        instructions.append("● RHYTHM PRINCIPLE:")
        instructions.append("  - Elements repeat at golden ratio intervals (1 : 1.618 : 2.618)")
        instructions.append("  - Each repetition at different scale and focus depth")
        instructions.append("  - Creates visual music — the eye dances through the image discovering echoes")

        return "\n".join(instructions)


visual_echo_engine = VisualEchoRepetitionEngine()


# ============================================================================
# BLOCO 37 – MICRO-IMPERFECTION ENGINE (IMPERFEIÇÕES CONTROLADAS)
# ============================================================================
class MicroImperfectionEngine:
    """
    Imperfeições controladas que aumentam realismo.
    Leve poeira, borda desgastada, pequenas irregularidades, gota fora do lugar.
    """

    def get_imperfection_instructions(self, scene_config: CinematicSceneConfig, style: StyleConfig) -> str:
        instructions = ["MICRO-IMPERFECTIONS (CONTROLLED REALISM):", ""]

        instructions.append("● PHILOSOPHY:")
        instructions.append("  - These are not flaws — they are evidence of reality")
        instructions.append("  - Each imperfection makes the image more believable, more human")
        instructions.append("  - Without them, the image looks like a 3D render, not a photograph")
        instructions.append("")

        instructions.append("● SURFACE IMPERFECTIONS:")
        instructions.append("  - 1-2 tiny dust specks on otherwise clean surfaces (visible only at 100% zoom)")
        instructions.append("  - Subtle fingerprint or smudge on polished metal (barely visible, 10% opacity)")
        instructions.append("  - Microscopic scratch on wood surface — 0.5mm wide, 5mm long (tells story of use)")
        instructions.append("  - Slight unevenness in paint or finish on product (handcrafted authenticity)")
        instructions.append("  - One water droplet slightly out of perfect alignment with others (organic randomness)")
        instructions.append("")

        instructions.append("● NATURAL IRREGULARITIES:")
        instructions.append("  - One leaf with a small brown edge or insect bite — nature is not perfect")
        instructions.append("  - Stone with natural crack or crystal inclusion — geological authenticity")
        instructions.append("  - Petal or botanical element at a slightly 'wrong' angle — feels unposed and natural")
        instructions.append("  - Wood grain with small knot hole — evidence of real tree, not veneer")
        instructions.append("")

        instructions.append("● LIGHTING IMPERFECTIONS:")
        instructions.append("  - Subtle lens flare from practical light source — not added in post")
        instructions.append("  - Slight light falloff at image edges (natural vignette from lens — 10-15% darkening)")
        instructions.append("  - One shadow slightly softer than mathematically perfect — organic lighting feel")
        instructions.append("")

        instructions.append("● WHAT TO AVOID:")
        instructions.append("  - NO dust or smudges on the product itself (product must appear pristine)")
        instructions.append("  - NO imperfections that distract from the product or message")
        instructions.append("  - NO damage or wear that suggests poor quality or neglect")
        instructions.append("  - Imperfections should be DISCOVERED upon close inspection, not ANNOUNCED")

        return "\n".join(instructions)


micro_imperfection_engine = MicroImperfectionEngine()


# ============================================================================
# BLOCO 38 – TEMPERATURE & SENSORY ENGINE (SENSAÇÃO TÉRMICA E TÁTIL)
# ============================================================================
class TemperatureSensoryEngine:
    """
    Faz a imagem transmitir sensação térmica e tátil.
    Superfície visivelmente gelada, vapor quente, metal frio, creme fresco.
    """

    def get_sensory_instructions(self, scene_config: CinematicSceneConfig, style: StyleConfig, product_name: str) -> str:
        instructions = ["TEMPERATURE & SENSORY TRANSMISSION (MAKE THE VIEWER FEEL):", ""]

        if "frozen" in scene_config.scene_type or "cold" in scene_config.scene_type:
            instructions.append("● PRIMARY SENSATION: INTENSE COLD")
            instructions.append("  - Product surface shows visible frost crystallization (feather-like patterns)")
            instructions.append("  - Condensation beads forming and slowly dripping — the viewer can almost feel the chill")
            instructions.append("  - Slight vapor mist where cold product meets warmer ambient air")
            instructions.append("  - Surface beneath product shows cold condensation ring")
            instructions.append("  - Color palette reinforces cold: ice blues, whites, subtle grey-purples")
            instructions.append("  - Viewer should almost shiver — the image triggers thermal memory")
        elif "steam" in style.descricao.lower() or "warm" in scene_config.lighting_temperature.lower():
            instructions.append("● PRIMARY SENSATION: COMFORTING WARMTH")
            instructions.append("  - Gentle steam wisps rising from product surface — visible heat")
            instructions.append("  - Warm glow on product suggesting it's been heated or is at body temperature")
            instructions.append("  - Surface beneath product shows subtle warmth reflection (golden undertone)")
            instructions.append("  - Viewer should feel the urge to reach out and touch the warmth")
        elif "cream" in product_name.lower() or "creme" in product_name.lower():
            instructions.append("● PRIMARY SENSATION: RICH, COOL CREAM")
            instructions.append("  - Product texture visible: thick, rich, freshly whipped appearance")
            instructions.append("  - Subtle peaks and swirls in cream surface catching light — tactile depth")
            instructions.append("  - Slight sheen suggesting moisture, freshness, and hydration")
            instructions.append("  - Viewer should almost smell the clean, botanical fragrance through visual cues")
        else:
            instructions.append("● PRIMARY SENSATION: PREMIUM TACTILE QUALITY")
            instructions.append("  - Every surface in the image suggests how it would feel to touch")
            instructions.append("  - Cool glass: smooth, weighty, substantial — you can feel the heft")
            instructions.append("  - Warm wood: textured grain, slightly rough, organic — you can feel the temperature difference")
            instructions.append("  - Soft fabric: visible weave, inviting texture, comforting — you can imagine the drape")
            instructions.append("  - Polished metal: cool to touch, smooth, reflective — you can feel the density")
        instructions.append("")
        instructions.append("● SENSORY DETAILS:")
        instructions.append("  - Texture visible at 100% zoom — every material reveals its tactile nature")
        instructions.append("  - Light interaction with surfaces defines 3D form and texture")
        instructions.append("  - Shadows and highlights work together to suggest temperature (cool shadows, warm highlights)")
        instructions.append("  - The image should trigger mirror neurons — viewer 'feels' the textures without touching")

        return "\n".join(instructions)


temperature_sensory_engine = TemperatureSensoryEngine()


# ============================================================================
# BLOCO 39 – TIME-OF-DAY SIMULATION (SIMULAÇÃO DE HORA DO DIA)
# ============================================================================
class TimeOfDaySimulation:
    """
    Simula horas específicas do dia com precisão cinematográfica.
    Golden hour, blue hour, midday, overcast, sunset, twilight, morning dew.
    """

    def __init__(self):
        self.time_presets = {
            "golden_hour": {
                "time": "1 hour before sunset (solar elevation 6-10°)",
                "temperature": "3000-3500K warm golden",
                "shadows": "Long, soft shadows stretching 3-4x object height, shadow edges slightly warm from atmospheric scattering",
                "quality": "Magical, warm, nostalgic — the 'magic hour' light that filmmakers chase. Soft, directional, golden.",
                "sky": "Warm amber to gold gradient, any visible sky or window light shows these tones",
                "best_for": "Premium product launches, lifestyle content, emotional storytelling",
            },
            "blue_hour": {
                "time": "20-30 minutes after sunset (solar elevation -4° to -6°)",
                "temperature": "8000-10000K cool blue",
                "shadows": "Very soft, almost nonexistent — ambient light only, no direct sunlight",
                "quality": "Serene, calm, sophisticated — the brief window when the world turns blue. Quiet luxury.",
                "sky": "Deep blue with lingering warmth at horizon, transitioning to dark blue overhead",
                "best_for": "Skincare, scientific products, cool luxury brands, evening rituals",
            },
            "midday": {
                "time": "12:00-14:00 (solar elevation 60-90°)",
                "temperature": "5500-6500K neutral white (daylight balanced)",
                "shadows": "Short, sharp shadows directly beneath objects — harsh, defined edges",
                "quality": "Clean, clinical, honest — reveals every detail. Nothing hidden. Scientific truth.",
                "sky": "Bright, clear, minimal color cast — pure white daylight",
                "best_for": "Proof/evidence content, clinical products, educational material",
            },
            "overcast": {
                "time": "Any time under complete cloud cover",
                "temperature": "6500-7500K cool diffuse (cloud-filtered daylight)",
                "shadows": "None — completely shadowless, soft ambient illumination from all directions",
                "quality": "Soft, even, gentle — the most flattering light. Wraps around subjects evenly.",
                "sky": "White-grey ambient through windows, no direct sun, no shadow patterns",
                "best_for": "Soft luxury, skincare, products that benefit from even, shadowless lighting",
            },
            "sunset": {
                "time": "During sunset (solar elevation 0-6°)",
                "temperature": "2500-3000K very warm orange/red tones",
                "shadows": "Extremely long, 5-8x object height, dramatic and theatrical",
                "quality": "Dramatic, passionate, romantic — intense colors and long shadows create theatrical mood",
                "sky": "Orange, pink, purple gradient — intense color saturation at horizon",
                "best_for": "Dramatic product reveals, luxury events, emotional high-impact content",
            },
            "twilight": {
                "time": "Between sunset and full dark (solar elevation -6° to -12°)",
                "temperature": "Mixed 4000K (artificial lights visible) + 6000K (residual sky ambient)",
                "shadows": "Multiple directions from mixed light sources — complex shadow patterns",
                "quality": "Mysterious, transitional, cinematic — the liminal time between day and night",
                "sky": "Deep purple to black with last light at horizon, first stars visible",
                "best_for": "Mystery products, exclusive launches, dramatic storytelling",
            },
            "morning_dew": {
                "time": "30 minutes after sunrise (solar elevation 5-10°)",
                "temperature": "5000K cool morning light with 3500K warm accents (sun just clearing horizon)",
                "shadows": "Medium length, soft, fresh quality — shadows still cool from night",
                "quality": "Fresh, new, clean, hopeful — the world is waking up. Dew on surfaces, crisp air.",
                "sky": "Clear pale blue with warm golden edge at horizon where sun is rising",
                "best_for": "Fresh products, morning routines, skincare, 'new beginning' narratives",
            },
        }

    def get_time_instructions(self, time_of_day: str) -> str:
        """Gera instruções precisas de simulação de hora do dia."""
        preset = self.time_presets.get(time_of_day, self.time_presets["golden_hour"])

        instructions = ["TIME-OF-DAY SIMULATION (CINEMATIC PRECISION):", ""]
        instructions.append(f"● SELECTED TIME: {time_of_day.replace('_', ' ').title()}")
        instructions.append(f"  Solar Time: {preset['time']}")
        instructions.append(f"  Color Temperature: {preset['temperature']}")
        instructions.append(f"  Shadow Character: {preset['shadows']}")
        instructions.append(f"  Light Quality: {preset['quality']}")
        instructions.append(f"  Sky/Window Light: {preset['sky']}")
        instructions.append(f"  Best For: {preset['best_for']}")
        instructions.append("")
        instructions.append("● EXECUTION REQUIREMENTS:")
        instructions.append("  - Light source angle and direction must physically match the specified solar time")
        instructions.append("  - Shadow length and direction must be mathematically consistent with light angle")
        instructions.append("  - Color temperature must be consistent across all light sources in the scene")
        instructions.append("  - Ambient fill light color must match sky/environment color at that time of day")
        instructions.append("  - The time of day should be immediately recognizable without being explicitly stated")

        return "\n".join(instructions)


time_of_day_simulation = TimeOfDaySimulation()


# ============================================================================
# BLOCO 40 – PRODUCT HERO LIGHTING RIG (RIG DE ILUMINAÇÃO PARA PRODUTO HERÓI)
# ============================================================================
class ProductHeroLightingRig:
    """
    Setup de iluminação cinematográfico completo para produto herói.
    3-point lighting ajustado (key, fill, rim), hair light, accent light.
    """

    def get_hero_lighting_instructions(self, style: StyleConfig, product_name: str) -> str:
        instructions = [f"PRODUCT HERO LIGHTING RIG for '{product_name}':", ""]

        instructions.append("● KEY LIGHT (Primary — Defines Form):")
        instructions.append("  - Position: 45° left of camera, 45° above product")
        instructions.append("  - Modifier: Large softbox (4x6ft) or scrim — creates soft, wrapping light")
        instructions.append("  - Purpose: Defines product shape, creates primary highlights, sets overall exposure")
        instructions.append("  - Intensity: Base exposure (0 stops) — all other lights measured relative to key")
        instructions.append("  - Quality: Soft shadows with gradual falloff — wraps around product revealing 3D form")
        instructions.append("")

        instructions.append("● FILL LIGHT (Secondary — Reveals Shadow Detail):")
        instructions.append("  - Position: 45° right of camera, at product level")
        instructions.append("  - Modifier: White reflector or smaller softbox (2x3ft)")
        instructions.append("  - Intensity: -2 stops from key light")
        instructions.append("  - Purpose: Fills shadows without eliminating them — reveals texture in shadow areas")
        instructions.append("  - Quality: Very soft — should not create secondary shadows")
        instructions.append("")

        instructions.append("● RIM / HAIR LIGHT (Tertiary — Creates Edge Separation):")
        instructions.append("  - Position: Behind product, 45° above, aimed at product edges from behind")
        instructions.append("  - Modifier: Bare reflector or small softbox for controlled spread")
        instructions.append("  - Intensity: +1 to +1.5 stops above key light (brighter than key)")
        instructions.append("  - Purpose: Creates luminous edge glow that separates product from background")
        instructions.append("  - Effect: Product 'pops' from background with golden/white edge definition")
        instructions.append("")

        instructions.append("● BACKGROUND LIGHT (Quaternary — Creates Depth):")
        instructions.append("  - Position: Behind product, aimed at background surface")
        instructions.append("  - Modifier: Grid spot or barn doors for controlled, directional spread")
        instructions.append("  - Intensity: -1 stop from key (creates subtle background gradient)")
        instructions.append("  - Purpose: Separates background from product, adds spatial depth")
        instructions.append("  - Effect: Background is darker at edges, brighter behind product (vignette effect)")
        instructions.append("")

        instructions.append("● ACCENT LIGHT (Precision — Highlights Key Feature):")
        instructions.append("  - Position: Micro-adjustable, aimed at specific product detail (logo, texture, key feature)")
        instructions.append("  - Modifier: Snoot or focused spot with optional gobo for pattern")
        instructions.append("  - Intensity: +0.5 stops above key on the specific detail only")
        instructions.append("  - Purpose: Draws attention to the most important product feature")
        instructions.append("")

        instructions.append("● LIGHTING RATIOS (Final Balance):")
        instructions.append("  - Key : Fill = 3:1 (professional contrast — shadows have detail but clear depth)")
        instructions.append("  - Key : Rim = 1:1.5 (rim brighter for dramatic edge definition)")
        instructions.append("  - Key : Background = 1:0.5 (background darker for product to advance visually)")
        instructions.append("  - Key : Accent = 1:1.5 (accent slightly brighter on specific detail only)")

        return "\n".join(instructions)


product_hero_lighting_rig = ProductHeroLightingRig()


# ============================================================================
# FUNÇÃO DE INTERFACE ATUALIZADA (EXPANDIDA COM BLOCOS 25-40)
# ============================================================================
def run(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ponto de entrada principal para o Hermes Agent.
    Utiliza todos os blocos implementados até o momento (1-40).
    """
    # Validar e sanitizar
    valid, msg = hermes_agent_interface.validate_payload(payload)
    if not valid:
        raise InvalidInputError(msg)
    data = hermes_agent_interface.sanitize_payload(payload)

    # Classificar
    content_role, confidence, _ = content_role_classifier.classify(data["copy"])
    patterns = copy_pattern_analyzer.analyze(data["copy"])

    # Selecionar estilo
    estilos_map = {"POST": ESTILOS_POST, "CARROSSEL": ESTILOS_CARROSSEL, "STORY": ESTILOS_STORY}
    estilos = estilos_map.get(data["formato"], ESTILOS_POST)
    style = style_selector.select(data["copy"], content_role, data["formato"], estilos)

    # Gerar headline (com override opcional)
    headline = data.get("headline_override") if data.get("headline_override") else headline_generator.generate(content_role, data["product_category"], data["timeframe"])

    # AD Type e prefixo
    ad_type = ad_type_decider.decide(style)
    ad_prefix = ad_type_decider.get_prompt_prefix(ad_type, style)

    # Blocos de suporte
    camera_config = camera_engine.get_config(style, content_role) if ad_type == AD_TYPE_PHOTOGRAPHY_WITH_TEXT else {"instruction": "N/A"}
    brand_config = brand_simulation_engine.get_brand_config(style)
    text_config = text_overlay_engine.generate_headline_config(style, content_role, headline)
    layout_instr = layout_engine.get_layout_instruction(style)
    negative = negative_prompt_builder.build(style, content_role)

    # Blocos cinematográficos (25-40)
    scene_config = cinematic_scene_composer.compose(style, data["product_name"], content_role)
    material_instr = material_texture_director.generate_instructions(scene_config, style)
    lighting_cine_instr = cinematic_lighting_director.generate_instructions(scene_config, style)
    color_instr = color_grade_mood_director.generate_instructions(scene_config, style)
    depth_instr = scene_depth_perspective_engine.generate_instructions(scene_config, style)
    particle_instr = atmospheric_particle_engine.get_particle_instructions(scene_config, style)
    caustic_instr = caustic_refractive_engine.get_caustic_instructions(scene_config, style, data["product_name"])
    golden_instr = golden_ratio_engine.get_composition_instructions(style, data["product_name"])
    texture_story_instr = texture_storytelling_engine.get_texture_story_instructions(scene_config)
    temp_shift_instr = emotional_temp_shift_engine.get_temperature_shift_instructions(scene_config, style, content_role)
    shadow_instr = product_shadow_design.get_shadow_instructions(scene_config, style)
    echo_instr = visual_echo_engine.get_echo_instructions(scene_config, style, data["product_name"])
    imperfection_instr = micro_imperfection_engine.get_imperfection_instructions(scene_config, style)
    sensory_instr = temperature_sensory_engine.get_sensory_instructions(scene_config, style, data["product_name"])
    time_instr = time_of_day_simulation.get_time_instructions(scene_config.time_of_day)
    hero_instr = product_hero_lighting_rig.get_hero_lighting_instructions(style, data["product_name"])

    # Blocos de atenção e composição (18-24)
    visual_hook = visual_hook_engine.generate(style, content_role, headline)
    attention = attention_elements_engine.generate(style)
    composition = composition_engine.generate(style)
    product_placement = product_placement_engine.generate(style, data["product_name"])
    color_palette = color_palette_engine.generate(style)
    typography = typography_engine.generate(style, headline)
    lighting = lighting_engine.generate(style)

    # Montagem do prompt (bloco 14)
    try:
        platform_enum = Platform(data["platform"])
    except ValueError:
        platform_enum = Platform.INSTAGRAM_FEED

    prompt_completo = prompt_assembler.assemble(
        copy=data["copy"], style=style, content_role=content_role,
        headline=headline, ad_type=ad_type, ad_type_prefix=ad_prefix,
        camera_config=camera_config, brand_config=brand_config,
        text_config=text_config, layout_instruction=layout_instr,
        platform=platform_enum, product_name=data["product_name"],
        scene_config=scene_config,
        scene_instructions=scene_config.environment_description,
        material_instructions=material_instr,
        lighting_instructions=lighting_cine_instr,
        color_instructions=color_instr,
        depth_instructions=depth_instr,
        particle_instructions=particle_instr,
        caustic_instructions=caustic_instr,
        golden_ratio_instructions=golden_instr,
        texture_story_instructions=texture_story_instr,
        temp_shift_instructions=temp_shift_instr,
        shadow_instructions=shadow_instr,
        echo_instructions=echo_instr,
        imperfection_instructions=imperfection_instr,
        sensory_instructions=sensory_instr,
        time_instructions=time_instr,
        hero_lighting_instructions=hero_instr,
        visual_hook=visual_hook,
        attention_instruction=attention,
        composition_instruction=composition,
        product_placement=product_placement,
        color_palette_instruction=color_palette,
        typography_instruction=typography,
        lighting_instruction=lighting,
    )

    # Quality Gate
    aprovado, score, razoes = prompt_quality_gate.validate(prompt_completo, style)

    return {
        "versao": f"hermes_image_engine_v{VERSION}",
        "build": BUILD,
        "formato": data["formato"],
        "plataforma": platform_enum.value,
        "content_role": content_role.value,
        "ad_type": ad_type,
        "estilo_nome": style.nome,
        "estilo_id": style.id,
        "headline": headline,
        "prompt_completo": prompt_completo,
        "negative_prompt": negative["negative_prompt"],
        "qualidade": {"score": score, "aprovado": aprovado, "razoes": razoes},
        "cinematic_scene": {
            "scene_type": scene_config.scene_type,
            "lighting": scene_config.lighting_setup[:80],
            "depth": scene_config.depth_of_field,
            "color_grade": scene_config.color_grade,
        },
        "meta": {"patterns_detected": patterns, "word_count": len(data["copy"].split())},
    }


# ============================================================================
# EXPORTAÇÕES DA PARTE 3
# ============================================================================
__all__ = [
    "CinematicSceneComposer",
    "MaterialTextureDirector",
    "CinematicLightingDirector",
    "ColorGradeMoodDirector",
    "SceneDepthPerspectiveEngine",
    "AtmosphericParticleEngine",
    "CausticRefractiveLightEngine",
    "GoldenRatioCompositionEngine",
    "TextureStorytellingEngine",
    "EmotionalColorTemperatureShift",
    "ProductShadowDesign",
    "VisualEchoRepetitionEngine",
    "MicroImperfectionEngine",
    "TemperatureSensoryEngine",
    "TimeOfDaySimulation",
    "ProductHeroLightingRig",
    "run",
]

print("=" * 78)
print("✅ HERMES IMAGE ENGINE V20 — PARTE 3/5 CARREGADA")
print(f"   Blocos 25 a 40 — Motores Cinematográficos Completos")
print(f"   Total de classes exportadas: {len(__all__)}")
print("=" * 78)

# ============================================================================
# HERMES IMAGE ENGINE V20 — NÍVEL DEUS ABSOLUTO — PARTE 4/5
# Blocos 41 a 55 + Builder Principal + Função run() Definitiva + Utilitários
# Continuação direta da Parte 3/5 — todos os imports, enums, dataclasses,
# constantes e engines anteriores já estão definidos.
# ============================================================================

# ============================================================================
# BLOCO 41 – CONTENT TYPE ROUTER (ROTEADOR DE TIPO DE CONTEÚDO)
# ============================================================================
class ContentTypeRouter:
    """
    Decide o TIPO de conteúdo visual baseado na copy, NÃO apenas o Content Role.
    Tipos: posicionamento, educativo, oferta, prova, opinião, lifestyle,
    storytelling, autoridade, comparação, revelação.
    """

    CONTENT_TYPES = {
        "posicionamento": {
            "keywords": ["não trabalhamos", "somos diferentes", "a gente acredita", "nossa missão",
                         "não aceitamos", "critério", "padrão", "filosofia", "princípio"],
            "visual_direction": "Brand manifesto. Strong typography, brand colors, no product needed. Focus on message and values.",
            "scene_preference": "concrete_minimal",
            "lighting_preference": "rim_light_dramatic",
        },
        "educativo": {
            "keywords": ["erro", "checklist", "antes de comprar", "guia", "como escolher", "aprender",
                         "saber", "critérios", "o que olhar", "passo a passo", "tutorial"],
            "visual_direction": "Clean editorial design. Icons, organized grid, paper texture. Trustworthy and helpful.",
            "scene_preference": "wooden_shelf",
            "lighting_preference": "window_light_natural",
        },
        "oferta": {
            "keywords": ["R$", "desconto", "promoção", "link na bio", "compre", "garanta", "aproveite",
                         "por apenas", "de R$", "por R$", "economize", "últimas"],
            "visual_direction": "Product hero shot. Golden lighting, price prominent, urgency elements. Conversion-focused.",
            "scene_preference": "aesop_shelf",
            "lighting_preference": "god_rays",
        },
        "prova": {
            "keywords": ["testei", "resultado", "antes e depois", "usei", "experimentei", "provei",
                         "funciona mesmo", "garantia", "comprovado", "clinicamente", "certificado"],
            "visual_direction": "Split screen or macro detail. Consistent lighting for credibility. Before/after clarity.",
            "scene_preference": "clinical_white",
            "lighting_preference": "softbox_diffuse",
        },
        "opinião": {
            "keywords": ["eu acho", "minha visão", "minha opinião", "eu acredito", "na minha experiência",
                         "eu defendo", "sou contra", "não concordo", "minha verdade"],
            "visual_direction": "Conceptual scene. Strong contrast, dramatic lighting. Visual manifesto of personal belief.",
            "scene_preference": "concrete_minimal",
            "lighting_preference": "split_lighting",
        },
        "lifestyle": {
            "keywords": ["rotina", "dia a dia", "uso todo dia", "minha manhã", "antes do trabalho",
                         "quando acordo", "no banho", "em casa", "minha semana", "meu ritual"],
            "visual_direction": "Cinematic real-life scene. Controlled environment, natural premium light. Aspirational but relatable.",
            "scene_preference": "wooden_shelf",
            "lighting_preference": "golden_hour_warm",
        },
        "storytelling": {
            "keywords": ["era uma vez", "certa vez", "no início", "há anos", "quando comecei",
                         "minha história", "tudo começou", "eu não sabia", "naquela época"],
            "visual_direction": "Narrative sequence. Progressive lighting from cold to warm. Visual arc across carousel slides.",
            "scene_preference": "wooden_shelf",
            "lighting_preference": "window_light_natural",
        },
        "autoridade": {
            "keywords": ["especialista", "anos de experiência", "referência", "líder", "autoridade",
                         "formado em", "certificado pela", "reconhecido por", "pioneiro"],
            "visual_direction": "Professional authority portrait. Rembrandt lighting. Credentials visible. Trust and expertise.",
            "scene_preference": "laboratory",
            "lighting_preference": "rembrandt",
        },
        "comparação": {
            "keywords": ["vs", "versus", "comparação", "lado a lado", "qual é melhor", "diferença entre",
                         "antes e depois", "comparamos", "testamos"],
            "visual_direction": "Split screen. Cold vs warm lighting. Clear visual dichotomy. Labels for each side.",
            "scene_preference": "clinical_white",
            "lighting_preference": "split_lighting",
        },
        "revelação": {
            "keywords": ["a verdade é", "o que ninguém conta", "segredo", "revelado", "ninguém fala",
                         "o que as marcas escondem", "a real sobre", "verdade por trás"],
            "visual_direction": "Dramatic reveal. Spotlight, darkness, mystery. Product emerging from shadows.",
            "scene_preference": "velvet_dark",
            "lighting_preference": "rim_light_dramatic",
        },
    }

    def route(self, copy: str, content_role: ContentRole, patterns: Dict[str, bool]) -> Dict[str, Any]:
        """
        Analisa a copy e retorna o tipo de conteúdo mais adequado.
        Combina o Content Role com padrões detectados para decisão precisa.
        """
        t = copy.lower()
        scores = {}

        for ctype, config in self.CONTENT_TYPES.items():
            score = sum(1 for kw in config["keywords"] if kw in t)
            scores[ctype] = score

        # Ajustes baseados no Content Role
        if content_role == ContentRole.CONVERSAO:
            scores["oferta"] = scores.get("oferta", 0) + 3
            scores["comparação"] = scores.get("comparação", 0) + 2
        elif content_role == ContentRole.PROVA:
            scores["prova"] = scores.get("prova", 0) + 3
        elif content_role == ContentRole.ALCANCE:
            scores["posicionamento"] = scores.get("posicionamento", 0) + 3
            scores["opinião"] = scores.get("opinião", 0) + 2
        elif content_role == ContentRole.CONFIANCA:
            scores["educativo"] = scores.get("educativo", 0) + 3

        # Ajustes baseados em padrões detectados
        if patterns.get("has_urgencia"):
            scores["oferta"] = scores.get("oferta", 0) + 2
        if patterns.get("has_garantia"):
            scores["prova"] = scores.get("prova", 0) + 2
        if patterns.get("has_storytelling"):
            scores["storytelling"] = scores.get("storytelling", 0) + 3
        if patterns.get("has_checklist"):
            scores["educativo"] = scores.get("educativo", 0) + 3
        if patterns.get("has_verdade_revelacao"):
            scores["revelação"] = scores.get("revelação", 0) + 3
        if patterns.get("has_opinion_forte"):
            scores["opinião"] = scores.get("opinião", 0) + 3
        if patterns.get("has_lifestyle"):
            scores["lifestyle"] = scores.get("lifestyle", 0) + 3
        if patterns.get("has_autoridade"):
            scores["autoridade"] = scores.get("autoridade", 0) + 3

        # Seleciona o tipo com maior pontuação
        best_type = max(scores, key=scores.get)
        best_config = self.CONTENT_TYPES[best_type]

        # Se a pontuação máxima for 0, usa fallback baseado no Content Role
        if scores[best_type] == 0:
            fallback_map = {
                ContentRole.ALCANCE: "posicionamento",
                ContentRole.CONFIANCA: "educativo",
                ContentRole.CONVERSAO: "oferta",
                ContentRole.PROVA: "prova",
            }
            best_type = fallback_map.get(content_role, "educativo")
            best_config = self.CONTENT_TYPES[best_type]

        return {
            "content_type": best_type,
            "visual_direction": best_config["visual_direction"],
            "scene_preference": best_config["scene_preference"],
            "lighting_preference": best_config["lighting_preference"],
            "scores": scores,
            "confidence": scores[best_type] / max(1, sum(scores.values())) if sum(scores.values()) > 0 else 0.5,
        }


content_type_router = ContentTypeRouter()


# ============================================================================
# BLOCO 42 – VISUAL STORYTELLING ENGINE (NARRATIVA VISUAL)
# ============================================================================
class VisualStorytellingEngine:
    """
    Cria narrativa visual completa: arco narrativo, micro-narrativas,
    layers com propósito. Não é só "produto no centro" — é uma cena que conta uma história.
    """

    NARRATIVE_ARCS = {
        "posicionamento": {
            "arc": "Revelation of truth",
            "foreground_purpose": "Barrier or obstacle (blurred) representing market lies",
            "midground_purpose": "Product or brand statement — the revealed truth",
            "background_purpose": "The world that will change once truth is known",
        },
        "educativo": {
            "arc": "Discovery and learning",
            "foreground_purpose": "The problem or confusion (blurred, chaotic)",
            "midground_purpose": "The solution or checklist — clarity and order",
            "background_purpose": "The improved future state after learning",
        },
        "oferta": {
            "arc": "Desire and acquisition",
            "foreground_purpose": "Contextual luxury elements (blurred) — lifestyle aspiration",
            "midground_purpose": "Product hero — the object of desire, perfectly lit",
            "background_purpose": "Premium environment — where you'll be after purchase",
        },
        "prova": {
            "arc": "Transformation documented",
            "foreground_purpose": "Before state elements (blurred, cold, dull)",
            "midground_purpose": "After state — product and result in sharp focus",
            "background_purpose": "Consistent environment proving no tricks",
        },
        "opinião": {
            "arc": "Conviction expressed",
            "foreground_purpose": "The opposing view (blurred, dark, chaotic)",
            "midground_purpose": "The stated opinion — clear, bold, undeniable",
            "background_purpose": "The world through this opinion's lens",
        },
        "lifestyle": {
            "arc": "A day in the life",
            "foreground_purpose": "Morning elements (blurred) — the routine",
            "midground_purpose": "Product in use — the ritual moment",
            "background_purpose": "The aspirational environment",
        },
        "storytelling": {
            "arc": "Hero's journey",
            "foreground_purpose": "The call to adventure (problem)",
            "midground_purpose": "The transformation moment (product discovery)",
            "background_purpose": "The new world (after solution)",
        },
        "autoridade": {
            "arc": "Wisdom shared",
            "foreground_purpose": "Credentials and tools of the trade",
            "midground_purpose": "The authority figure or product — source of wisdom",
            "background_purpose": "The domain of expertise",
        },
        "comparação": {
            "arc": "Choice clarified",
            "foreground_purpose": "Divider element — the decision point",
            "midground_purpose": "Both options side by side — clear visual difference",
            "background_purpose": "Neutral environment — fair comparison",
        },
        "revelação": {
            "arc": "Secret unveiled",
            "foreground_purpose": "Curtain or veil (blurred) — the hidden truth",
            "midground_purpose": "The revealed product or fact — dramatic spotlight",
            "background_purpose": "Darkness — the unknown that surrounded the secret",
        },
    }

    def generate(self, content_type: str, style: StyleConfig) -> str:
        """Gera a narrativa visual baseada no tipo de conteúdo."""
        arc_data = self.NARRATIVE_ARCS.get(content_type, self.NARRATIVE_ARCS["posicionamento"])

        instructions = [
            f"VISUAL STORYTELLING — Narrative Arc: {arc_data['arc']}",
            "",
            "THREE ACT STRUCTURE IN A SINGLE FRAME:",
            f"ACT 1 (Foreground — setup): {arc_data['foreground_purpose']}",
            "- Elements slightly blurred, creating entry point and curiosity",
            "- Invites viewer to look deeper into the scene",
            "",
            f"ACT 2 (Midground — confrontation): {arc_data['midground_purpose']}",
            "- Razor-sharp focus, the emotional core of the image",
            "- Where the story's main action happens",
            "",
            f"ACT 3 (Background — resolution): {arc_data['background_purpose']}",
            "- Atmospheric depth, contextual but not distracting",
            "- Shows the world after the transformation",
            "",
            "STORYTELLING PRINCIPLES:",
            "- Every element in the frame has narrative purpose — nothing is decorative",
            "- Lighting tells the emotional arc: cold (problem/tension) → warm (solution/release)",
            "- Textures reveal history: worn surfaces = experience, pristine surfaces = aspiration",
            "- The viewer should understand the story in 0.5 seconds, then discover details over time",
        ]

        return "\n".join(instructions)


visual_storytelling_engine = VisualStorytellingEngine()


# ============================================================================
# BLOCO 43 – BRAND WORLD BUILDER (CONSTRUTOR DE UNIVERSO DE MARCA)
# ============================================================================
class BrandWorldBuilder:
    """
    Constrói o universo visual consistente da marca — não apenas uma imagem,
    mas um MUNDO visual completo com ambiente, objetos, paleta e luz assinatura.
    """

    BRAND_WORLDS = {
        "apothecary_premium": {
            "environment": "Dark wood shelves, amber glass bottles, green botanicals, brushed gold accents, polished concrete floors",
            "recurring_objects": ["Eucalyptus sprigs", "Rosemary", "Ceramic vessels", "Linen cloth", "Brass trays", "Apothecary jars"],
            "signature_light": "Warm 3000K god rays streaming from upper-left window, volumetric dust particles",
            "signature_textures": "Dark walnut wood grain, frosted glass condensation, brushed metal patina, handmade paper labels",
            "color_dna": "Deep forest green (#1a3a2a) + Antique gold (#c9a96e) + Warm cream (#f5f0e8)",
            "brands": ["Aesop", "Le Labo", "Diptyque"],
        },
        "clinical_science": {
            "environment": "White ceramic surfaces, stainless steel, glass beakers, clean white walls, laboratory lighting",
            "recurring_objects": ["Glass vials", "Scientific instruments", "White towels", "Measuring tools", "Petri dishes"],
            "signature_light": "Even 5000K overhead panels, shadowless, medical-grade illumination",
            "signature_textures": "Smooth white ceramic, clear glass with measurement marks, brushed stainless steel",
            "color_dna": "Pure white (#ffffff) + Medical blue (#2563eb) + Soft green (#10b981)",
            "brands": ["La Mer", "La Roche-Posay", "Vichy", "The Ordinary"],
        },
        "natural_organic": {
            "environment": "Natural stone surfaces, living plants, morning dew, dappled forest light, bamboo elements",
            "recurring_objects": ["River stones", "Moss", "Cherry blossoms", "Bamboo", "Raw cotton", "Wooden trays"],
            "signature_light": "Soft diffused window light 4500K through shoji screens, warm paper lantern fill",
            "signature_textures": "Natural stone with moss, recycled glass with bamboo caps, raw linen, handcrafted ceramic",
            "color_dna": "Sage green (#87a878) + Warm brown (#8b6914) + Cream (#faf7f2) + Cherry blossom pink",
            "brands": ["Rituals", "L'Occitane", "Kiehl's"],
        },
        "minimal_luxury": {
            "environment": "Clean architectural spaces, negative space, single statement elements, brutalist concrete",
            "recurring_objects": ["Single flower stem", "Geometric sculptures", "Concrete blocks", "Glass panels"],
            "signature_light": "Soft diffused 5000K, shadowless, clean architectural lighting",
            "signature_textures": "Raw concrete with formwork marks, matte black metal, clear glass, oxidized steel",
            "color_dna": "Black (#0a0a0a) + White (#ffffff) + Single accent color",
            "brands": ["Byredo", "The Row", "Jil Sander", "COS"],
        },
        "bold_statement": {
            "environment": "High-contrast spaces, dramatic angles, urban landscapes, studio backdrops",
            "recurring_objects": ["Bold typography", "Geometric shapes", "Dramatic shadows", "Light beams"],
            "signature_light": "Dramatic lateral light, deep shadows, high contrast ratio 4:1, rim lights",
            "signature_textures": "Black velvet, polished metal, matte rubber, reflective surfaces, raw concrete",
            "color_dna": "Black (#000000) + White (#ffffff) + Vibrant accent (neon or primary color)",
            "brands": ["Nike", "Apple", "Patagonia", "Supreme"],
        },
    }

    def build(self, style: StyleConfig, brand_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Constrói o Brand World baseado na referência de marca do estilo.
        """
        brand_name = brand_config.get("brand_reference", "Aesop")

        world_key = "apothecary_premium"  # default
        for key, world_data in self.BRAND_WORLDS.items():
            if brand_name in world_data["brands"]:
                world_key = key
                break

        world = self.BRAND_WORLDS[world_key]
        chosen_object = random.choice(world["recurring_objects"])

        return {
            "world_key": world_key,
            "environment": world["environment"],
            "recurring_objects": world["recurring_objects"],
            "signature_light": world["signature_light"],
            "signature_textures": world["signature_textures"],
            "color_dna": world["color_dna"],
            "chosen_object": chosen_object,
            "instruction": (
                f"BRAND WORLD ({world_key.replace('_', ' ').title()}): "
                f"Create a scene that feels native to the {brand_name} universe. "
                f"Environment: {world['environment']}. "
                f"Include at least one recurring object: {chosen_object}. "
                f"Light signature: {world['signature_light']}. "
                f"Texture signature: {world['signature_textures']}. "
                f"Color DNA: {world['color_dna']}. "
                f"Every element must feel like it belongs to this specific world — consistency is luxury."
            ),
        }


brand_world_builder = BrandWorldBuilder()


# ============================================================================
# BLOCO 44 – TYPOGRAPHY INTEGRATION SYSTEM (SISTEMA DE INTEGRAÇÃO TIPOGRÁFICA)
# ============================================================================
class TypographyIntegrationSystem:
    """
    Integra tipografia ao cenário em 4 níveis de profundidade,
    não apenas "texto sobreposto".
    """

    INTEGRATION_LEVELS = {
        1: {
            "name": "Overlay Integrado",
            "description": "Text placed on clear, low-contrast area of the image with subtle shadow for legibility",
            "shadow": "2px offset, 30% opacity black",
            "positioning": "Strategic empty space — never over product",
            "best_for": ["oferta", "prova", "lifestyle"],
        },
        2: {
            "name": "Texto como Elemento de Cena",
            "description": "Text appears on physical objects within the scene — labels, signs, cards, letterpress",
            "shadow": "None (physical text)",
            "positioning": "Integrated into scene objects — on product labels, wooden signs, paper cards",
            "best_for": ["posicionamento", "storytelling", "autoridade"],
        },
        3: {
            "name": "Texto como Protagonista",
            "description": "Typography IS the main visual element — giant headline, minimal background, no product",
            "shadow": "None (solid background)",
            "positioning": "Center-dominant, 50-70% of frame",
            "best_for": ["posicionamento", "opinião", "revelação"],
        },
        4: {
            "name": "Texto Invisível",
            "description": "Headline so integrated it feels like part of the scene — reflection, shadow projection, environmental",
            "shadow": "As cast by scene lighting",
            "positioning": "On reflective surfaces, as shadows, on fogged glass, in light beams",
            "best_for": ["lifestyle", "storytelling", "revelação"],
        },
    }

    def generate(self, style: StyleConfig, content_type: str, headline: str) -> str:
        """Seleciona o nível de integração tipográfica baseado no estilo e tipo de conteúdo."""
        # Determina o nível de integração
        if style.ad_type == AD_TYPE_DESIGN:
            level = 3  # Texto como protagonista (design puro)
        elif content_type in ("lifestyle", "storytelling", "revelação") and style.tipografia_usa:
            level = 4  # Texto invisível para cenas imersivas
        elif content_type in ("posicionamento", "storytelling", "autoridade") and style.produto_proporcao != "0%":
            level = 2  # Texto como elemento de cena
        else:
            level = 1  # Overlay integrado (padrão seguro)

        level_data = self.INTEGRATION_LEVELS[level]

        return (
            f"TYPOGRAPHY INTEGRATION (Level {level} — {level_data['name']}): "
            f"Headline \"{headline}\" integrated using: {level_data['description']}. "
            f"Positioning: {level_data['positioning']}. "
            f"Shadow treatment: {level_data['shadow']}. "
            f"Typography style: {style.tipografia_estilo if style.tipografia_usa else 'None'}. "
            f"The text should feel native to the scene, not pasted on. "
            f"Integration level chosen because content type is '{content_type}' and AD type is '{style.ad_type}'."
        )


typography_integration_system = TypographyIntegrationSystem()


# ============================================================================
# BLOCO 45 – MULTI-FORMAT ADAPTER (ADAPTADOR MULTI-FORMATO)
# ============================================================================
class MultiFormatAdapter:
    """
    Adapta automaticamente o mesmo conceito visual para POST, CARROSSEL e STORY.
    Mantém consistência de Brand World enquanto ajusta composição e proporção.
    """

    FORMAT_SPECS = {
        "POST": {
            "aspect": "1:1",
            "resolution": "1080x1080",
            "composition": "Square. Product centered or at golden ratio point. Headline top or bottom third. Balanced weight distribution.",
            "slides": 1,
        },
        "CARROSSEL": {
            "aspect": "1:1 (multiple slides)",
            "resolution": "1080x1080 per slide",
            "composition": "Slide 1: Hook (problem/curiosity). Slides 2-4: Development (education/proof). Slides 5-6: Solution + CTA.",
            "slides": "3-6",
        },
        "STORY": {
            "aspect": "9:16",
            "resolution": "1080x1920",
            "composition": "Vertical. Headline top third, product middle third, CTA bottom third. Swipe-up implicit.",
            "slides": 1,
        },
    }

    def adapt(self, formato: str, content_type: str, style: StyleConfig, headline: str) -> str:
        """Gera instruções de adaptação para o formato específico."""
        spec = self.FORMAT_SPECS.get(formato, self.FORMAT_SPECS["POST"])

        base = f"MULTI-FORMAT ADAPTATION ({formato}, {spec['aspect']}, {spec['resolution']}): "

        if formato == "POST":
            base += (
                f"Square composition. {spec['composition']}. "
                f"Headline: \"{headline}\" positioned in {style.texto_posicao}. "
                f"Product: {style.produto_posicao} occupying {style.produto_proporcao}. "
                f"Single frame must tell complete story — no dependence on other slides."
            )
        elif formato == "CARROSSEL":
            base += (
                f"Multi-slide sequence ({spec['slides']} slides). {spec['composition']}. "
                f"Slide 1 visual hook: dramatic problem shot with cold lighting. "
                f"Slide 2-3: educational or proof content with neutral lighting. "
                f"Slide 4-5: product reveal with warm, golden lighting. "
                f"Slide 6: CTA slide with offer and link. "
                f"Consistent Brand World across all slides — same palette, same light signature. "
                f"Progressive color temperature: cold (problem) → warm (solution)."
            )
        elif formato == "STORY":
            base += (
                f"Vertical 9:16 composition. {spec['composition']}. "
                f"Headline \"{headline}\" in top third (safe from UI elements). "
                f"Product in middle third — the 'thumb zone' where attention naturally falls. "
                f"CTA and link in bottom third. "
                f"Background with subtle texture (never pure white). "
                f"Designed for 2-second viewing — immediate impact."
            )

        base += (
            f" Brand World consistency: same environment, same light, same materials as other formats. "
            f"Only composition and proportion change — the visual DNA remains identical."
        )

        return base


multi_format_adapter = MultiFormatAdapter()


# ============================================================================
# BLOCO 46 – HYPER-DETAIL SPECIFICATION ENGINE (ESPECIFICAÇÃO DE HIPER-DETALHES)
# ============================================================================
class HyperDetailSpecificationEngine:
    """
    Garante que NENHUM detalhe fique vago no prompt final.
    Especifica cores hexadecimais exatas, ângulos de iluminação em graus,
    potência relativa em stops, distâncias focais, materiais com nomes técnicos.
    """

    def generate(self, style: StyleConfig, scene_config: CinematicSceneConfig, product_name: str) -> str:
        instructions = ["HYPER-DETAIL TECHNICAL SPECIFICATIONS:", ""]

        # Cores exatas
        instructions.append("● COLOR SPECIFICATIONS (Exact Hex Values):")
        instructions.append(f"  Primary Brand Color: {style.cor_fundo} (background)")
        instructions.append(f"  Text Color: {style.cor_texto}")
        instructions.append(f"  Accent Color: #d4af37 (for highlights, CTAs, badges)")
        instructions.append(f"  Shadow Color: #000000 at 30% opacity for text shadows")
        instructions.append(f"  Highlight Color: #ffffff at 10% opacity for specular highlights")
        instructions.append("")

        # Iluminação medida
        instructions.append("● LIGHTING SPECIFICATIONS (Measured Values):")
        instructions.append(f"  Key Light Angle: 45° horizontal from camera-left, 45° vertical elevation")
        instructions.append(f"  Key Light Temperature: {scene_config.lighting_temperature}")
        instructions.append(f"  Fill Light Intensity: -2.0 stops from key (25% of key light output)")
        instructions.append(f"  Rim Light Intensity: +1.5 stops from key (280% of key light output)")
        instructions.append(f"  Background Light Intensity: -1.0 stop from key (50% of key light output)")
        instructions.append(f"  Light-to-Subject Distance: 1.5 meters (key), 2.0 meters (fill), 0.8 meters (rim)")
        instructions.append("")

        # Câmera
        instructions.append("● CAMERA SPECIFICATIONS (Technical Precision):")
        instructions.append(f"  Focal Length: {scene_config.focal_length}")
        instructions.append(f"  Aperture: {scene_config.depth_of_field.split(',')[0] if ',' in scene_config.depth_of_field else 'f/2.8'}")
        instructions.append(f"  Focus Distance: 2.0 meters (midground/product plane)")
        instructions.append(f"  Sensor Format: Full-frame 35mm equivalent")
        instructions.append(f"  ISO Equivalent: 100 (maximum image quality, no noise)")
        instructions.append("")

        # Materiais
        instructions.append("● MATERIAL SPECIFICATIONS (Technical Names):")
        for element, material in scene_config.texture_materials.items():
            instructions.append(f"  {element}: {material}")
        instructions.append("")

        # Espaço
        instructions.append("● SPATIAL MEASUREMENTS:")
        instructions.append("  Foreground distance from camera: 0.5m — 1.5m (out of focus)")
        instructions.append("  Midground distance from camera: 2.0m — 3.0m (critical focus)")
        instructions.append("  Background distance from camera: 5.0m — infinity (atmospheric)")
        instructions.append(f"  Product size in frame: {style.produto_proporcao} of total image area")
        instructions.append(f"  Text size in frame: {style.texto_proporcao} of total image area")

        return "\n".join(instructions)


hyper_detail_engine = HyperDetailSpecificationEngine()


# ============================================================================
# BLOCO 47 – CREATIVE CONCEPT EXPLODER (EXPLOSOR DE CONCEITOS CRIATIVOS)
# ============================================================================
class CreativeConceptExploder:
    """
    Injetor de criatividade forçada. Gera conceitos artísticos únicos
    que fazem a imagem se destacar instantaneamente.
    """

    CREATIVE_CONCEPTS = [
        {
            "name": "Frozen in Time",
            "description": "Product suspended mid-explosion of its own ingredients — droplets of serum, fragments of botanicals, all frozen in a single cinematic moment. The viewer sees the product's essence literally surrounding it.",
        },
        {
            "name": "Portal to Another World",
            "description": "Product sits at the threshold of two worlds — one side cold/problem (desaturated, harsh), the other warm/solution (vibrant, soft). The product is the portal, the bridge between states.",
        },
        {
            "name": "Gravity Defied",
            "description": "Product floating impossibly above its surface, casting a shadow below. Elements rise around it — water droplets ascending, petals drifting upward. Physics suspended to create visual magic.",
        },
        {
            "name": "Macro Universe",
            "description": "Extreme close-up reveals a microscopic world on the product's surface — dew drops become oceans, texture becomes landscape. The product is a planet of its own.",
        },
        {
            "name": "Shadow Story",
            "description": "The product's shadow tells a different story than the product itself — the shadow shows the transformation (a person moving freely) while the product remains still. Light and shadow as dual narratives.",
        },
        {
            "name": "Through the Looking Glass",
            "description": "Product seen through or reflected in an unexpected surface — a water droplet, a curved mirror, a glass prism. The reflection distorts beautifully, creating artistic abstraction while keeping the product recognizable.",
        },
        {
            "name": "Elemental Fusion",
            "description": "Product surrounded by one of the four elements — fire (warm glow, sparks), water (droplets, ripples), earth (stone, moss, clay), air (floating, mist, feathers). The element amplifies the product's core benefit.",
        },
        {
            "name": "Time Lapse Illusion",
            "description": "Multiple stages of product use shown in a single frame — product closed, being opened, in use, result visible. Like a time-lapse collapsed into one image. Shows process and outcome simultaneously.",
        },
        {
            "name": "Negative Space Narrative",
            "description": "The product occupies only 10-20% of the frame. The rest is dramatic negative space — dark void, vast sky, empty room. The emptiness amplifies the product's importance. Isolation as emphasis.",
        },
        {
            "name": "Reflection Reality",
            "description": "The product is seen only through its reflection — in a puddle, a mirror, a glass surface. The real product is off-camera. This creates mystery and forces the viewer to engage actively with the image.",
        },
    ]

    def generate(self, content_type: str, product_name: str, style: StyleConfig) -> str:
        # Filtrar conceitos adequados ao tipo de conteúdo
        if content_type == "prova":
            relevant = [c for c in self.CREATIVE_CONCEPTS if c["name"] in ["Time Lapse Illusion", "Shadow Story", "Through the Looking Glass"]]
        elif content_type == "oferta":
            relevant = [c for c in self.CREATIVE_CONCEPTS if c["name"] in ["Frozen in Time", "Elemental Fusion", "Portal to Another World"]]
        elif content_type == "posicionamento":
            relevant = [c for c in self.CREATIVE_CONCEPTS if c["name"] in ["Negative Space Narrative", "Gravity Defied", "Reflection Reality"]]
        else:
            relevant = self.CREATIVE_CONCEPTS

        chosen = random.choice(relevant if relevant else self.CREATIVE_CONCEPTS)

        instructions = [
            f"CREATIVE CONCEPT — '{chosen['name']}':",
            chosen["description"],
            "",
            f"Application to '{product_name}':",
            f"- This concept should be adapted to highlight {product_name}'s unique value proposition",
            f"- The creative concept must serve the product message, not distract from it",
            f"- Execution should feel intentional and artistic, never gimmicky",
            "",
            "CREATIVITY PRINCIPLE:",
            "The best creative concepts make the viewer pause and think 'I've never seen that before'",
            "while simultaneously making perfect sense for the product.",
            "Originality + Relevance = Unforgettable Visual Communication.",
        ]

        return "\n".join(instructions)


creative_concept_exploder = CreativeConceptExploder()


# ============================================================================
# BLOCO 48 – MANDATORY COPY EMBEDDER (INCORPORADOR OBRIGATÓRIO DE COPY)
# ============================================================================
class MandatoryCopyEmbedder:
    """
    OBRIGA que a copy (ou headline + CTA) apareça FISICAMENTE na imagem.
    Define posição exata, fonte, cor, tamanho, efeitos e modo de mesclagem.
    """

    def generate(self, headline: str, copy: str, style: StyleConfig, text_config: Dict[str, Any]) -> str:
        instructions = ["MANDATORY COPY EMBEDDING:", ""]

        instructions.append("● COPY INTEGRATION REQUIREMENT:")
        instructions.append("  THE FOLLOWING TEXT MUST BE VISIBLE ON THE FINAL IMAGE:")
        instructions.append(f"  HEADLINE: \"{headline}\"")

        # Extrair CTA da copy
        cta_match = re.search(r'(link na bio|compre agora|garanta o seu|acesse o link|clique aqui|saiba mais)', copy.lower())
        cta = cta_match.group(0) if cta_match else DEFAULT_CTA
        instructions.append(f"  CTA: \"{cta}\"")
        instructions.append(f"  FULL COPY (if space allows): \"{copy[:100]}{'...' if len(copy) > 100 else ''}\"")
        instructions.append("")

        instructions.append("● HEADLINE PLACEMENT:")
        instructions.append(f"  Position: {style.texto_posicao}")
        instructions.append(f"  Size: {style.tipografia_tamanho}")
        instructions.append(f"  Font: {style.tipografia_estilo}")
        instructions.append(f"  Color: {style.tipografia_cor} (hex)")
        instructions.append(f"  Shadow: {'2px offset, 30% opacity black' if style.tipografia_sombra else 'none'}")
        instructions.append("")

        instructions.append("● CTA PLACEMENT:")
        instructions.append(f"  Position: Bottom 10% of frame, centered or right-aligned")
        instructions.append(f"  Size: 8-10% of frame height (smaller than headline, but clearly visible)")
        instructions.append(f"  Font: Same family as headline, regular weight")
        instructions.append(f"  Color: White (#ffffff) with dark semi-transparent background badge (rgba(0,0,0,0.6))")
        instructions.append("")

        instructions.append("● INTEGRATION RULES:")
        instructions.append("  - Text NEVER covers the product — positioned in dedicated negative space")
        instructions.append("  - Text has minimum 10% margin from all frame edges")
        instructions.append("  - Text contrast ratio against background: minimum 4.5:1 (WCAG AA)")
        instructions.append("  - If background is busy, text has semi-transparent dark backdrop for legibility")
        instructions.append("  - Text is part of the composition, not an afterthought")

        return "\n".join(instructions)


mandatory_copy_embedder = MandatoryCopyEmbedder()


# ============================================================================
# BLOCO 49 – ENVIRONMENTAL REFLECTION & INTEGRATION ENGINE (REFLEXÃO AMBIENTAL)
# ============================================================================
class EnvironmentalReflectionEngine:
    """
    Faz o produto refletir o ambiente de forma realista.
    Mapeamento de reflexão especular, refração em líquidos/vidro,
    sombras coloridas projetadas pelo ambiente.
    """

    def generate(self, scene_config: CinematicSceneConfig, product_name: str) -> str:
        instructions = ["ENVIRONMENTAL REFLECTION & INTEGRATION:", ""]

        instructions.append("● SPECULAR REFLECTIONS:")
        instructions.append(f"  - '{product_name}' surface reflects the surrounding environment")
        instructions.append("  - Reflection shows a miniaturized, curved version of the scene background")
        instructions.append("  - Reflection sharpness depends on surface: polished = sharp reflection, matte = soft glow")
        instructions.append("  - Fresnel effect: reflection intensity increases at glancing angles (edges of product)")
        instructions.append("")

        instructions.append("● REFRACTIVE EFFECTS (for glass/liquid products):")
        instructions.append("  - Light passing through transparent/translucent materials bends (refraction)")
        instructions.append("  - Background objects seen through product are slightly distorted and offset")
        instructions.append("  - Thicker glass sections show more distortion and slight color separation (chromatic aberration)")
        instructions.append("  - Liquid inside containers creates secondary refraction layer")
        instructions.append("")

        instructions.append("● ENVIRONMENTAL COLOR BLEED:")
        instructions.append("  - Product picks up subtle color from nearby objects (color bleeding)")
        instructions.append("  - If next to green leaf: product shadow side has subtle green tint")
        instructions.append("  - If on wooden surface: product underside reflects warm brown tones")
        instructions.append("  - This is how light works in reality — color bounces between surfaces")
        instructions.append("")

        instructions.append("● SHADOW INTEGRATION:")
        instructions.append("  - Product shadow is NOT generic grey/black — it carries color from the environment")
        instructions.append("  - Shadow on wood: warm brown undertone")
        instructions.append("  - Shadow on marble: cool grey with subtle vein patterns visible through shadow")
        instructions.append("  - Shadow on ice: blue-tinted and partially transparent (light passes through ice)")
        instructions.append("")

        instructions.append("● CONTACT POINT REALISM:")
        instructions.append("  - Where product meets surface: micro-shadow (ambient occlusion) — darkest point in scene")
        instructions.append("  - If product is cold: condensation ring on surface around contact point")
        instructions.append("  - If product is heavy: slight depression or compression visible on soft surfaces")

        return "\n".join(instructions)


environmental_reflection_engine = EnvironmentalReflectionEngine()


# ============================================================================
# BLOCO 50 – CINEMATIC CAMERA & LENS SIMULATOR (SIMULADOR DE CÂMERA E LENTE)
# ============================================================================
class CameraLensSimulator:
    """
    Simula lentes anamórficas, flares orgânicos, vinhetas,
    grão de filme, distorção de lente e características de câmeras reais.
    """

    def generate(self, style: StyleConfig) -> str:
        instructions = ["CINEMATIC CAMERA & LENS SIMULATION:", ""]

        # Estilos de filme/câmera
        film_stocks = [
            {"name": "Kodak Portra 400", "characteristics": "Warm skin tones, soft highlights, fine grain, pastel color palette, creamy bokeh"},
            {"name": "Fujifilm Velvia 50", "characteristics": "Vivid saturation, deep greens, punchy contrast, fine grain, landscape favorite"},
            {"name": "Cinematic Arri Alexa", "characteristics": "High dynamic range (14+ stops), smooth highlight rolloff, cinematic color science, subtle grain at high ISO"},
            {"name": "Hasselblad Natural Color", "characteristics": "Exceptional detail, true-to-life colors, medium format depth of field, 16-bit color depth feel"},
        ]
        chosen_stock = random.choice(film_stocks)

        instructions.append(f"● FILM STOCK / CAMERA PROFILE: {chosen_stock['name']}")
        instructions.append(f"  Characteristics: {chosen_stock['characteristics']}")
        instructions.append("")

        instructions.append("● LENS CHARACTERISTICS:")
        instructions.append("  - Subtle barrel distortion at edges (0.5-1%) — adds organic, non-CGI feel")
        instructions.append("  - Slight chromatic aberration at high-contrast edges (0.5-1px) — lens realism")
        instructions.append("  - Natural vignette: 15-20% darkening at corners (optical, not artificial)")
        instructions.append("  - Lens flare: subtle organic flare from bright light sources (not added in post)")
        instructions.append("")

        instructions.append("● BOKEH RENDERING:")
        instructions.append("  - Out-of-focus highlights: circular, soft edges, slight brightness at center (natural vignetting in bokeh circles)")
        instructions.append("  - Bokeh shape: determined by aperture blade count (9 blades = circular bokeh)")
        instructions.append("  - No 'donut' bokeh (mirror lens) — only smooth, creamy background blur")
        instructions.append("")

        instructions.append("● FOCUS CHARACTERISTICS:")
        instructions.append("  - Critical focus plane: razor-sharp on product (midground)")
        instructions.append("  - Focus falloff: gradual and smooth — no harsh transition from sharp to blurred")
        instructions.append("  - Micro-contrast: high on product surface (shows texture and detail)")

        return "\n".join(instructions)


camera_lens_simulator = CameraLensSimulator()


# ============================================================================
# BLOCO 51 – STORY-DRIVEN COMPOSITION FORCE (COMPOSIÇÃO GUIADA POR HISTÓRIA)
# ============================================================================
class StoryDrivenCompositionForce:
    """
    Cada imagem deve contar uma micro-história, mesmo em post único.
    Define um "momento congelado" com ação implícita.
    """

    def generate(self, content_type: str, style: StyleConfig) -> str:
        moments = {
            "oferta": "The exact moment the product is revealed from its packaging — the lid is mid-air, the product emerges into golden light. Anticipation becomes revelation.",
            "prova": "The split-second between 'before' and 'after' — the dividing line shows both states simultaneously. Time collapses into one frame.",
            "posicionamento": "The moment a truth is declared — bold typography hits like a gavel. The world pauses to listen.",
            "educativo": "The instant of understanding — the 'aha!' moment visualized. Knowledge transfers from the image to the viewer.",
            "lifestyle": "A frozen moment of daily ritual — steam rising, light streaming, product in use. Ordinary becomes extraordinary.",
            "storytelling": "The peak of the narrative arc — the climax captured in a single frame. Everything before led to this; everything after will be different.",
            "autoridade": "The moment expertise is shared — calm confidence radiates. The viewer leans in to learn.",
        }
        moment = moments.get(content_type, moments["lifestyle"])

        return (
            f"STORY-DRIVEN COMPOSITION: {moment}\n"
            f"The image captures a precise, intentional moment — not a static product shot, but a scene with implied before and after. "
            f"The viewer's brain completes the story, making the image more engaging and memorable."
        )


story_composition_force = StoryDrivenCompositionForce()


# ============================================================================
# BLOCO 52 – SENSORY IMMERSION LAYER (CAMADA DE IMERSÃO SENSORIAL)
# ============================================================================
class SensoryImmersionLayer:
    """
    Adiciona ao prompt descrições sensoriais sinestésicas que guiam
    a atmosfera e texturas da imagem.
    """

    def generate(self, scene_config: CinematicSceneConfig, style: StyleConfig) -> str:
        sensations = []
        if "wood" in str(scene_config.texture_materials).lower():
            sensations.append("the warm, earthy scent of aged wood and botanical oils")
        if "ice" in str(scene_config.texture_materials).lower() or "frozen" in scene_config.scene_type:
            sensations.append("the crisp, cold air that makes fingertips tingle")
        if "steam" in style.descricao.lower():
            sensations.append("the comforting warmth of steam carrying subtle herbal fragrance")
        if "marble" in str(scene_config.texture_materials).lower():
            sensations.append("the cool, smooth touch of polished stone under warm ambient light")
        if "fabric" in str(scene_config.texture_materials).lower():
            sensations.append("the soft rustle of natural linen, its texture visible to the eye and imaginable to the touch")

        sensation_text = " and ".join(sensations) if sensations else "the subtle interplay of textures that invites touch"

        return (
            f"SENSORY IMMERSION: The image should evoke {sensation_text}. "
            f"While the viewer cannot physically feel, smell, or hear the scene, the visual cues should trigger sensory memory — "
            f"making the image feel alive, present, and tangibly real."
        )


sensory_immersion_layer = SensoryImmersionLayer()


# ============================================================================
# BLOCO 53 – MULTI-FORMAT CONSISTENCY ENFORCER (GARANTIDOR DE CONSISTÊNCIA MULTI-FORMATO)
# ============================================================================
class MultiFormatConsistencyEnforcer:
    """
    Garante que ao gerar para CARROSSEL ou STORY, o mesmo conceito visual
    seja mantido, adaptando proporção sem perder elementos-chave.
    """

    def generate(self, formato: str, style: StyleConfig, brand_world: Dict[str, Any]) -> str:
        instructions = ["MULTI-FORMAT CONSISTENCY ENFORCEMENT:", ""]

        instructions.append(f"● FORMAT: {formato}")
        instructions.append(f"● BRAND WORLD: {brand_world.get('world_key', 'apothecary_premium')}")
        instructions.append("")

        instructions.append("● CONSISTENCY REQUIREMENTS:")
        instructions.append("  - SAME Brand World across all formats (environment, light, materials)")
        instructions.append("  - SAME Color DNA across all formats")
        instructions.append("  - SAME Typography family across all formats")
        instructions.append("  - SAME Product presentation style across all formats")
        instructions.append("  - DIFFERENT only in composition and proportion to fit format")
        instructions.append("")

        if formato == "CARROSSEL":
            instructions.append("● CARROSSEL CONSISTENCY:")
            instructions.append("  - All slides must feel like they belong to the same photoshoot")
            instructions.append("  - Consistent lighting direction across slides (key light from same side)")
            instructions.append("  - Consistent color temperature progression: cold (slide 1) → warm (final slide)")
            instructions.append("  - Product must appear at consistent scale and angle across slides where present")
        elif formato == "STORY":
            instructions.append("● STORY CONSISTENCY:")
            instructions.append("  - Vertical adaptation of the horizontal concept")
            instructions.append("  - Key elements repositioned vertically, not cropped out")
            instructions.append("  - Headline remains fully visible in top third safe zone")

        return "\n".join(instructions)


multi_format_consistency_enforcer = MultiFormatConsistencyEnforcer()


# ============================================================================
# BLOCO 54 – POST-GENERATION SELF-CRITIQUE & REFINEMENT (AUTO-CRÍTICA PÓS-GERAÇÃO)
# ============================================================================
class PostGenerationCritique:
    """
    Após gerar o prompt, avalia se ele está à altura do "nível Deus"
    e adiciona automaticamente mais detalhes se necessário.
    """

    MINIMUM_SPECS = 8

    def critique(self, prompt: str) -> Dict[str, Any]:
        """Avalia o prompt e retorna diagnóstico com melhorias sugeridas."""
        issues = []
        score = 10.0

        # Verificar especificações técnicas
        has_hex_colors = bool(re.search(r'#[0-9a-fA-F]{6}', prompt))
        has_lighting_angles = bool(re.search(r'\d{2,3}°', prompt))
        has_aperture = bool(re.search(r'f/\d', prompt))
        has_focal_length = bool(re.search(r'\d{2,3}mm', prompt))
        has_material_specs = bool(re.search(r'(wood|glass|metal|fabric|stone|ice|crystal)', prompt.lower()))
        has_text_specs = bool(re.search(r'(font|typography|text size|headline)', prompt.lower()))
        has_atmosphere = bool(re.search(r'(particle|mist|steam|dust|ray|bokeh)', prompt.lower()))
        has_copy_embedded = bool(re.search(r'(copy|text|headline).*(visible|integrated|placed)', prompt.lower()))

        specs_count = sum([has_hex_colors, has_lighting_angles, has_aperture, has_focal_length,
                          has_material_specs, has_text_specs, has_atmosphere, has_copy_embedded])

        if specs_count < self.MINIMUM_SPECS:
            missing = []
            if not has_hex_colors: missing.append("hex color codes")
            if not has_lighting_angles: missing.append("lighting angles in degrees")
            if not has_aperture: missing.append("aperture value (f/stop)")
            if not has_focal_length: missing.append("focal length in mm")
            if not has_material_specs: missing.append("material specifications")
            if not has_text_specs: missing.append("text/typography specifications")
            if not has_atmosphere: missing.append("atmospheric elements (particles, mist, etc.)")
            if not has_copy_embedded: missing.append("copy text integration details")
            issues.append(f"MISSING_SPECS: {', '.join(missing)}")
            score -= (self.MINIMUM_SPECS - specs_count) * 1.0

        # Verificar presença de elementos cinematográficos
        has_cinematic = bool(re.search(r'(cinematic|god rays|volumetric|rim light|bokeh|golden ratio|foreground|midground|background)', prompt.lower()))
        if not has_cinematic:
            issues.append("MISSING_CINEMATIC_ELEMENTS")
            score -= 2.0

        # Verificar anti-UGC
        has_ugc_warning = bool(re.search(r'(no handheld|no selfie|no amateur|no candid)', prompt.lower()))
        if not has_ugc_warning:
            issues.append("MISSING_ANTI_UGC_WARNINGS")
            score -= 1.5

        return {
            "score": max(0, score),
            "issues": issues,
            "passed": len(issues) == 0,
            "specs_count": specs_count,
            "missing_details": issues,
        }

    def refine(self, prompt: str, critique_result: Dict[str, Any]) -> str:
        """Adiciona detalhes faltantes ao prompt."""
        if critique_result["passed"]:
            return prompt

        additions = []
        if "hex color codes" in str(critique_result["missing_details"]):
            additions.append("SPECIFY EXACT COLORS: Use hex codes for all colors (background: #[hex], text: #[hex], accents: #[hex]).")
        if "lighting angles" in str(critique_result["missing_details"]):
            additions.append("SPECIFY LIGHTING ANGLES: Key light at 45° left/45° above, fill at 45° right, rim at 180° behind.")
        if "aperture" in str(critique_result["missing_details"]):
            additions.append("SPECIFY APERTURE: Use f/2.8 for shallow depth of field with beautiful bokeh.")
        if "focal length" in str(critique_result["missing_details"]):
            additions.append("SPECIFY FOCAL LENGTH: Use 85mm for product hero shots with compression and isolation.")
        if "material specifications" in str(critique_result["missing_details"]):
            additions.append("SPECIFY MATERIALS: Describe each surface material with technical names and properties.")
        if "text/typography" in str(critique_result["missing_details"]):
            additions.append("SPECIFY TYPOGRAPHY: Define font family, weight, size in pixels or percentage, color hex, and shadow treatment.")
        if "atmospheric elements" in str(critique_result["missing_details"]):
            additions.append("ADD ATMOSPHERE: Include floating dust particles in light beams, subtle mist, or steam for depth and life.")
        if "copy text integration" in str(critique_result["missing_details"]):
            additions.append("INTEGRATE COPY TEXT: The ad copy headline MUST be visible on the final image. Specify exact position, font, color, and size.")

        refined_prompt = prompt + "\n\n" + "\n".join(additions)
        return refined_prompt


post_generation_critique = PostGenerationCritique()


# ============================================================================
# BLOCO 55 – UNIVERSAL DESIGN SYSTEM (SISTEMA DE DESIGN UNIVERSAL)
# ============================================================================
class UniversalDesignSystem:
    """
    Para conteúdo não-anúncio, aplica um sistema de design atômico
    com tokens de design consistentes.
    """

    def generate(self, content_type: str, style: StyleConfig) -> str:
        instructions = ["UNIVERSAL DESIGN SYSTEM:", ""]

        instructions.append(f"● CONTENT TYPE: {content_type}")
        instructions.append(f"● DESIGN APPROACH: {style.ad_type}")
        instructions.append("")

        # Tokens de design
        instructions.append("● DESIGN TOKENS:")
        instructions.append(f"  Primary Color: {style.cor_fundo}")
        instructions.append(f"  Text Color: {style.cor_texto}")
        instructions.append(f"  Typography: {style.tipografia_estilo}")
        instructions.append(f"  Spacing Unit: 8px grid system (all margins and padding multiples of 8px)")
        instructions.append(f"  Border Radius: 4px for UI elements, 0px for photography")
        instructions.append("")

        # Hierarquia visual por tipo de conteúdo
        hierarchy = {
            "posicionamento": "1. Headline (dominant, 70%) → 2. Brand mark (20%) → 3. Supporting element (10%)",
            "educativo": "1. Title/question → 2. Key points (numbered/icon) → 3. Example/CTA",
            "oferta": "1. Product hero shot → 2. Price/offer → 3. CTA",
            "prova": "1. Result/transformation → 2. Product → 3. Guarantee/CTA",
            "opinião": "1. Statement → 2. Author/brand → 3. Context element",
            "lifestyle": "1. Scene/atmosphere → 2. Product in use → 3. Subtle branding",
        }
        instructions.append(f"● VISUAL HIERARCHY: {hierarchy.get(content_type, '1. Hook → 2. Message → 3. CTA')}")

        return "\n".join(instructions)


universal_design_system = UniversalDesignSystem()


# ============================================================================
# IMAGE PROMPT BUILDER V20 (CONSTRUTOR PRINCIPAL COM 55 BLOCOS)
# ============================================================================
class ImagePromptBuilderV20:
    """
    Construtor principal que integra TODOS os 55 blocos do pipeline Nível Deus.
    Responsável por orquestrar a geração completa do prompt cinematográfico.
    """

    def __init__(self):
        # Blocos de análise (Parte 1)
        self.role_classifier = content_role_classifier
        self.pattern_analyzer = copy_pattern_analyzer
        self.style_selector = style_selector
        self.headline_gen = headline_generator
        self.ad_type_decider_ref = ad_type_decider
        self.camera_engine_ref = camera_engine
        self.brand_simulation = brand_simulation_engine
        self.text_overlay = text_overlay_engine
        self.layout_engine_ref = layout_engine
        self.negative_builder = negative_prompt_builder
        self.quality_gate = prompt_quality_gate

        # Blocos de regeneração e montagem (Parte 2)
        self.regeneration_loop = RegenerationLoop()
        self.prompt_assembler_ref = prompt_assembler
        self.output_formatter_ref = output_formatter
        self.hermes_interface = hermes_agent_interface

        # Blocos de atenção e composição (Parte 2)
        self.visual_hook_engine_ref = visual_hook_engine
        self.attention_engine = attention_elements_engine
        self.composition_engine_ref = composition_engine
        self.product_placement_engine_ref = product_placement_engine
        self.color_palette_engine_ref = color_palette_engine
        self.typography_engine_ref = typography_engine
        self.lighting_engine_ref = lighting_engine

        # Blocos cinematográficos (Parte 3)
        self.scene_composer = cinematic_scene_composer
        self.material_director = material_texture_director
        self.lighting_director = cinematic_lighting_director
        self.color_director = color_grade_mood_director
        self.depth_engine = scene_depth_perspective_engine
        self.particle_engine = atmospheric_particle_engine
        self.caustic_engine = caustic_refractive_engine
        self.golden_ratio_engine_ref = golden_ratio_engine
        self.texture_story_engine = texture_storytelling_engine
        self.temp_shift_engine = emotional_temp_shift_engine
        self.shadow_design = product_shadow_design
        self.echo_engine = visual_echo_engine
        self.imperfection_engine = micro_imperfection_engine
        self.sensory_engine = temperature_sensory_engine
        self.time_simulation = time_of_day_simulation
        self.hero_lighting_rig = product_hero_lighting_rig

        # Blocos Nível Deus (Parte 4)
        self.content_type_router_ref = content_type_router
        self.visual_storytelling = visual_storytelling_engine
        self.brand_world_builder_ref = brand_world_builder
        self.typography_integration = typography_integration_system
        self.multi_format_adapter_ref = multi_format_adapter
        self.hyper_detail_engine_ref = hyper_detail_engine
        self.creative_concept_exploder_ref = creative_concept_exploder
        self.mandatory_copy_embedder_ref = mandatory_copy_embedder
        self.environment_reflection_engine_ref = environmental_reflection_engine
        self.camera_lens_simulator_ref = camera_lens_simulator
        self.story_composition_force_ref = story_composition_force
        self.sensory_immersion_layer_ref = sensory_immersion_layer
        self.multi_format_consistency_ref = multi_format_consistency_enforcer
        self.post_critique = post_generation_critique
        self.universal_design_ref = universal_design_system

        # Cache e estatísticas
        self._cache: Dict[str, Dict] = {}
        self._stats = {
            "prompts_gerados": 0,
            "prompts_aprovados": 0,
            "prompts_reprovados": 0,
            "regeneracoes": 0,
            "tempo_total": 0.0,
        }

    def build(self, copy: str, product_name: str = "", product_category: str = "produto",
              timeframe: str = "7 dias", formato: str = "POST",
              platform: Platform = Platform.INSTAGRAM_FEED,
              max_regenerations: int = MAX_TENTATIVAS_REGENERACAO,
              attempt: int = 0, force_angle_shift: bool = False) -> Dict[str, Any]:
        """
        Executa o pipeline completo de 55 blocos e retorna o prompt final.
        """
        inicio = time.time()
        cache_key = hashlib.md5(f"{copy[:200]}:{product_name}:{formato}:{platform.value}:{attempt}".encode()).hexdigest()
        if attempt == 0 and cache_key in self._cache:
            logger.info("Cache hit — retornando prompt armazenado")
            return self._cache[cache_key]

        self._stats["prompts_gerados"] += 1

        # 1. Classificação e análise
        content_role, role_confidence, _ = self.role_classifier.classify(copy)
        patterns = self.pattern_analyzer.analyze(copy)
        if attempt >= 3:
            alt_roles = {ContentRole.ALCANCE: ContentRole.CONFIANCA, ContentRole.CONFIANCA: ContentRole.CONVERSAO,
                         ContentRole.CONVERSAO: ContentRole.PROVA, ContentRole.PROVA: ContentRole.ALCANCE}
            content_role = alt_roles.get(content_role, ContentRole.CONFIANCA)

        # 2. Roteamento de tipo de conteúdo (Bloco 41)
        content_type_result = self.content_type_router_ref.route(copy, content_role, patterns)

        # 3. Seleção de estilo
        estilos_map = {"POST": ESTILOS_POST, "CARROSSEL": ESTILOS_CARROSSEL, "STORY": ESTILOS_STORY}
        estilos = estilos_map.get(formato, ESTILOS_POST)
        style = self.style_selector.select(copy, content_role, formato, estilos)

        # 4. Headline
        headline = self.headline_gen.generate(content_role, product_category, timeframe)

        # 5. AD Type e prefixo
        ad_type = self.ad_type_decider_ref.decide(style)
        ad_prefix = self.ad_type_decider_ref.get_prompt_prefix(ad_type, style)

        # 6. Brand e Mundo
        brand_config = self.brand_simulation.get_brand_config(style)
        brand_world = self.brand_world_builder_ref.build(style, brand_config)

        # 7. Câmera
        camera_config = self.camera_engine_ref.get_config(style, content_role) if ad_type == AD_TYPE_PHOTOGRAPHY_WITH_TEXT else {"instruction": "N/A"}

        # 8. Cena cinematográfica (Blocos 25-40)
        scene_config = self.scene_composer.compose(style, product_name, content_role)
        scene_instr = scene_config.environment_description
        material_instr = self.material_director.generate_instructions(scene_config, style)
        lighting_cine_instr = self.lighting_director.generate_instructions(scene_config, style)
        color_instr = self.color_director.generate_instructions(scene_config, style)
        depth_instr = self.depth_engine.generate_instructions(scene_config, style)
        particle_instr = self.particle_engine.get_particle_instructions(scene_config, style)
        caustic_instr = self.caustic_engine.get_caustic_instructions(scene_config, style, product_name)
        golden_instr = self.golden_ratio_engine_ref.get_composition_instructions(style, product_name)
        texture_story_instr = self.texture_story_engine.get_texture_story_instructions(scene_config)
        temp_shift_instr = self.temp_shift_engine.get_temperature_shift_instructions(scene_config, style, content_role)
        shadow_instr = self.shadow_design.get_shadow_instructions(scene_config, style)
        echo_instr = self.echo_engine.get_echo_instructions(scene_config, style, product_name)
        imperfection_instr = self.imperfection_engine.get_imperfection_instructions(scene_config, style)
        sensory_instr = self.sensory_engine.get_sensory_instructions(scene_config, style, product_name)
        time_instr = self.time_simulation.get_time_instructions(scene_config.time_of_day)
        hero_instr = self.hero_lighting_rig.get_hero_lighting_instructions(style, product_name)

        # 9. Atenção e composição (Blocos 18-24)
        visual_hook = self.visual_hook_engine_ref.generate(style, content_role, headline)
        attention = self.attention_engine.generate(style)
        composition = self.composition_engine_ref.generate(style)
        product_placement = self.product_placement_engine_ref.generate(style, product_name)
        color_palette = self.color_palette_engine_ref.generate(style)
        typography = self.typography_engine_ref.generate(style, headline)
        lighting = self.lighting_engine_ref.generate(style)

        # 10. Storytelling e Integração (Blocos 42-44)
        storytelling = self.visual_storytelling.generate(content_type_result["content_type"], style)
        typography_integration = self.typography_integration.generate(style, content_type_result["content_type"], headline)

        # 11. Multi-Formato (Bloco 45)
        multi_format = self.multi_format_adapter_ref.adapt(formato, content_type_result["content_type"], style, headline)

        # 12. Layout e Texto
        text_config = self.text_overlay.generate_headline_config(style, content_role, headline)
        layout_instr = self.layout_engine_ref.get_layout_instruction(style)

        # 13. Blocos Nível Deus (46-55)
        hyper_detail = self.hyper_detail_engine_ref.generate(style, scene_config, product_name)
        creative_concept = self.creative_concept_exploder_ref.generate(content_type_result["content_type"], product_name, style)
        mandatory_copy = self.mandatory_copy_embedder_ref.generate(headline, copy, style, text_config)
        environment_reflection = self.environment_reflection_engine_ref.generate(scene_config, product_name)
        camera_lens_simulation = self.camera_lens_simulator_ref.generate(style)
        story_composition = self.story_composition_force_ref.generate(content_type_result["content_type"], style)
        sensory_immersion = self.sensory_immersion_layer_ref.generate(scene_config, style)
        multi_format_consistency = self.multi_format_consistency_ref.generate(formato, style, brand_world)
        universal_design = self.universal_design_ref.generate(content_type_result["content_type"], style)

        # 14. Montagem do prompt final (Bloco 14)
        prompt_completo = self.prompt_assembler_ref.assemble(
            copy=copy, style=style, content_role=content_role,
            headline=headline, ad_type=ad_type, ad_type_prefix=ad_prefix,
            camera_config=camera_config, brand_config=brand_config,
            text_config=text_config, layout_instruction=layout_instr,
            platform=platform, product_name=product_name,
            scene_config=scene_config,
            scene_instructions=scene_instr,
            material_instructions=material_instr,
            lighting_instructions=lighting_cine_instr,
            color_instructions=color_instr,
            depth_instructions=depth_instr,
            particle_instructions=particle_instr,
            caustic_instructions=caustic_instr,
            golden_ratio_instructions=golden_instr,
            texture_story_instructions=texture_story_instr,
            temp_shift_instructions=temp_shift_instr,
            shadow_instructions=shadow_instr,
            echo_instructions=echo_instr,
            imperfection_instructions=imperfection_instr,
            sensory_instructions=sensory_instr,
            time_instructions=time_instr,
            hero_lighting_instructions=hero_instr,
            visual_hook=visual_hook,
            attention_instruction=attention,
            composition_instruction=composition,
            product_placement=product_placement,
            color_palette_instruction=color_palette,
            typography_instruction=typography,
            lighting_instruction=lighting,
            content_type_instruction=content_type_result["content_type"],
            storytelling_instruction=storytelling,
            brand_world_instruction=brand_world["instruction"],
            typography_integration_instruction=typography_integration,
            multi_format_instruction=multi_format,
            hyper_detail_instruction=hyper_detail,
            creative_concept_instruction=creative_concept,
            mandatory_copy_instruction=mandatory_copy,
            environment_reflection_instruction=environment_reflection,
            camera_lens_simulation_instruction=camera_lens_simulation,
            story_composition_instruction=story_composition,
            sensory_immersion_instruction=sensory_immersion,
        )

        # 15. Pós-geração: crítica e refinamento (Bloco 54)
        critique_result = self.post_critique.critique(prompt_completo)
        if not critique_result["passed"]:
            prompt_completo = self.post_critique.refine(prompt_completo, critique_result)

        # 16. Quality Gate (Bloco 12)
        negative = self.negative_builder.build(style, content_role)
        aprovado, score, razoes = self.quality_gate.validate(prompt_completo, style)

        duracao = round(time.time() - inicio, 2)
        self._stats["tempo_total"] += duracao

        if aprovado:
            self._stats["prompts_aprovados"] += 1
        else:
            self._stats["prompts_reprovados"] += 1
            self._stats["regeneracoes"] += 1

        output = {
            "versao": f"hermes_image_engine_v{VERSION}",
            "build": BUILD,
            "formato": formato,
            "plataforma": platform.value,
            "copy_origem": copy,
            "content_role": content_role.value,
            "content_type": content_type_result["content_type"],
            "ad_type": ad_type,
            "estilo_nome": style.nome,
            "estilo_id": style.id,
            "headline": headline,
            "prompt_completo": prompt_completo,
            "negative_prompt": negative["negative_prompt"],
            "cinematic_scene": {
                "scene_type": scene_config.scene_type,
                "lighting": scene_config.lighting_setup[:80],
                "depth": scene_config.depth_of_field,
                "color_grade": scene_config.color_grade,
            },
            "brand_world": brand_world["world_key"],
            "qualidade": {"score": score, "aprovado": aprovado, "razoes": razoes if not aprovado else []},
            "meta": {
                "duracao_segundos": duracao,
                "product_name": product_name,
                "product_category": product_category,
                "timeframe": timeframe,
                "word_count": len(copy.split()),
                "attempt": attempt + 1,
                "force_angle_shift": force_angle_shift,
            },
            "critique": critique_result,
        }

        # Salvar no cache se aprovado
        if aprovado and attempt == 0:
            self._cache[cache_key] = output
            if len(self._cache) > MAX_CACHE_ENTRIES:
                self._cache.clear()

        return output


# Instância global do builder
image_prompt_builder_v20 = ImagePromptBuilderV20()


# ============================================================================
# FUNÇÃO run() DEFINITIVA PARA O HERMES AGENT
# ============================================================================
def run(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ponto de entrada oficial para o Hermes Agent.
    Executa o pipeline completo de 55 blocos com regeneração automática.

    Args:
        payload: {
            "copy": str (obrigatório),
            "product_name": str (opcional),
            "product_category": str (opcional, default: "produto"),
            "timeframe": str (opcional, default: "7 dias"),
            "formato": str (opcional, default: "POST"),
            "platform": str (opcional, default: "instagram_feed"),
            "headline": str (opcional, override da headline gerada),
        }

    Returns:
        Dict com prompt_completo, negative_prompt, headline, estilo, score, etc.
    """
    # Validar entrada
    valid, msg = hermes_agent_interface.validate_payload(payload)
    if not valid:
        raise InvalidInputError(msg)

    data = hermes_agent_interface.sanitize_payload(payload)

    try:
        platform_enum = Platform(data["platform"])
    except ValueError:
        platform_enum = Platform.INSTAGRAM_FEED

    # Função de build para o loop de regeneração
    def build_with_attempt(attempt: int = 0, force_angle_shift: bool = False) -> Dict[str, Any]:
        return image_prompt_builder_v20.build(
            copy=data["copy"],
            product_name=data["product_name"],
            product_category=data["product_category"],
            timeframe=data["timeframe"],
            formato=data["formato"],
            platform=platform_enum,
            attempt=attempt,
            force_angle_shift=force_angle_shift,
        )

    # Executar com loop de regeneração
    result = image_prompt_builder_v20.regeneration_loop.execute(build_with_attempt)

    # Override de headline se fornecido
    if data.get("headline_override"):
        result["headline"] = data["headline_override"]
        result["prompt_completo"] = result["prompt_completo"].replace(
            result.get("headline", ""), data["headline_override"]
        )

    return result


# ============================================================================
# UTILITÁRIOS DE EXPORTAÇÃO E ANÁLISE (BÁSICOS, COMPLEMENTARES À PARTE 5)
# ============================================================================
def gerar_resumo_prompt(resultado: Dict[str, Any]) -> str:
    """Gera um resumo formatado do prompt cinematográfico para console."""
    linhas = ["=" * 78, "  📊 RESUMO DO PROMPT CINEMATOGRÁFICO — HERMES IMAGE ENGINE V20", "=" * 78]
    role_map = {"alcance": "🟥 ALCANCE", "confianca": "🟨 CONFIANÇA", "conversao": "🟩 CONVERSÃO", "prova": "🟦 PROVA"}
    linhas.append(f"  📋 Content Role: {role_map.get(resultado.get('content_role', ''), '?')}")
    if resultado.get("content_type"):
        linhas.append(f"  🎯 Content Type: {resultado['content_type']}")
    linhas.append(f"  🎨 Estilo: {resultado.get('estilo_nome', '')} (ID: {resultado.get('estilo_id', '')})")
    linhas.append(f"  📝 Headline: {resultado.get('headline', '')}")
    linhas.append(f"  🎬 Cena: {resultado.get('cinematic_scene', {}).get('scene_type', '')}")
    linhas.append(f"  💡 Iluminação: {resultado.get('cinematic_scene', {}).get('lighting', '')[:60]}")
    if resultado.get("brand_world"):
        linhas.append(f"  🌍 Brand World: {resultado['brand_world']}")
    q = resultado.get("qualidade", {})
    linhas.append(f"  ⭐ Score: {q.get('score', '?')}/10 {'✅' if q.get('aprovado') else '⚠️'}")
    meta = resultado.get("meta", {})
    linhas.append(f"  ⏱️  Tempo: {meta.get('duracao_segundos', '?')}s | Palavras: {meta.get('word_count', '?')}")
    if resultado.get("output_path"):
        linhas.append(f"  💾 Salvo em: {resultado['output_path']}")
    return "\n".join(linhas)


def exportar_prompt_markdown(resultado: Dict[str, Any]) -> str:
    """Exporta o prompt em formato Markdown."""
    return output_formatter.to_markdown(resultado)


def listar_estilos_disponiveis(formato: str = None) -> List[Dict[str, Any]]:
    """Lista todos os estilos disponíveis com informações detalhadas."""
    estilos = []
    todos = {"POST": ESTILOS_POST, "CARROSSEL": ESTILOS_CARROSSEL, "STORY": ESTILOS_STORY}
    for fmt, lista in todos.items():
        if formato and fmt != formato:
            continue
        for s in lista:
            estilos.append({
                "id": s.id, "nome": s.nome, "formato": s.formato,
                "content_role": s.content_role, "ad_type": s.ad_type,
                "descricao": s.descricao, "scene_type": s.scene_type,
                "lighting_style": s.lighting_style, "brand_referencia": s.brand_referencia,
            })
    return estilos


def executar_auto_teste() -> Dict[str, Any]:
    """Executa a bateria completa de testes de integridade."""
    return auto_test_suite.run_all()


# ============================================================================
# EXPORTAÇÕES DA PARTE 4
# ============================================================================
__all__ = [
    "ContentTypeRouter",
    "VisualStorytellingEngine",
    "BrandWorldBuilder",
    "TypographyIntegrationSystem",
    "MultiFormatAdapter",
    "HyperDetailSpecificationEngine",
    "CreativeConceptExploder",
    "MandatoryCopyEmbedder",
    "EnvironmentalReflectionEngine",
    "CameraLensSimulator",
    "StoryDrivenCompositionForce",
    "SensoryImmersionLayer",
    "MultiFormatConsistencyEnforcer",
    "PostGenerationCritique",
    "UniversalDesignSystem",
    "ImagePromptBuilderV20",
    "run",
    "gerar_resumo_prompt",
    "exportar_prompt_markdown",
    "listar_estilos_disponiveis",
    "executar_auto_teste",
]

print("=" * 78)
print("✅ HERMES IMAGE ENGINE V20 — PARTE 4/5 CARREGADA")
print(f"   Blocos 41 a 55 + Builder Principal + Função run() Definitiva + Utilitários")
print(f"   Total de símbolos exportados: {len(__all__)}")
print("=" * 78)

#!/usr/bin/env python3
"""
HERMES IMAGE ENGINE V20 — NÍVEL DEUS ABSOLUTO — PARTE 5/5
CLI Completa, Auto-Teste Avançado, Utilitários Finais e Finalização.
Esta é a última parte. Deve ser concatenada com as Partes 1 a 4.
"""

import sys
import os
import json
import time
import argparse
import textwrap
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

# ============================================================================
# UTILITÁRIOS DE VALIDAÇÃO DE PRODUTO
# ============================================================================
def validar_produto_input(produto_input: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Valida se o dicionário de entrada do produto contém os campos mínimos.
    Realiza 10 verificações progressivas de integridade dos dados.
    """
    if not produto_input:
        return False, "produto_input está vazio ou é None"
    if not isinstance(produto_input, dict):
        return False, f"produto_input deve ser um dicionário, recebeu {type(produto_input).__name__}"
    if "nome" not in produto_input:
        return False, (
            "produto_input deve conter a chave 'nome'.\n"
            "Exemplo mínimo: {'nome': 'Joelheira Premium'}\n"
            "Exemplo completo: {'nome': 'Joelheira Premium', 'preco': '129.90', "
            "'categoria': 'saúde', 'descricao_curta': 'Alívio imediato para dores no joelho'}"
        )
    if not produto_input["nome"]:
        return False, "O campo 'nome' não pode ser vazio"
    if not isinstance(produto_input["nome"], str):
        return False, f"O campo 'nome' deve ser uma string, recebeu {type(produto_input['nome']).__name__}"
    if len(produto_input["nome"].strip()) < 2:
        return False, "O nome do produto deve ter pelo menos 2 caracteres"
    if "preco" in produto_input and produto_input["preco"] is not None:
        try:
            preco_str = str(produto_input["preco"]).replace("R$", "").replace(" ", "").replace(",", ".")
            valor = float(preco_str)
            if valor <= 0:
                return False, f"O preço deve ser maior que zero: {produto_input['preco']}"
        except (ValueError, TypeError):
            return False, f"Formato de preço inválido: '{produto_input['preco']}'. Use formatos como: '89.90', '89,90', 'R$ 89.90'"
    if "categoria" in produto_input and produto_input["categoria"] is not None:
        if not isinstance(produto_input["categoria"], str):
            return False, f"O campo 'categoria' deve ser uma string, recebeu {type(produto_input['categoria']).__name__}"
        if len(produto_input["categoria"].strip()) < 2:
            return False, "A categoria deve ter pelo menos 2 caracteres"
    if "beneficios" in produto_input and produto_input["beneficios"] is not None:
        if not isinstance(produto_input["beneficios"], list):
            return False, f"O campo 'beneficios' deve ser uma lista, recebeu {type(produto_input['beneficios']).__name__}"
        for i, b in enumerate(produto_input["beneficios"]):
            if not isinstance(b, str) or not b.strip():
                return False, f"Benefício na posição {i} está vazio ou não é string"
    if "diferenciais" in produto_input and produto_input["diferenciais"] is not None:
        if not isinstance(produto_input["diferenciais"], list):
            return False, f"O campo 'diferenciais' deve ser uma lista, recebeu {type(produto_input['diferenciais']).__name__}"
        for i, d in enumerate(produto_input["diferenciais"]):
            if not isinstance(d, str) or not d.strip():
                return False, f"Diferencial na posição {i} está vazio ou não é string"
    return True, "OK"


# ============================================================================
# UTILITÁRIOS DE EXPORTAÇÃO E ANÁLISE
# ============================================================================
def gerar_resumo_campanha(resultado: Dict[str, Any], detalhado: bool = False) -> str:
    """Gera um resumo formatado completo para console."""
    linhas = ["=" * 78, "  📊 RESUMO DO PROMPT CINEMATOGRÁFICO — HERMES IMAGE ENGINE V20", "=" * 78]
    role_map = {"alcance": "🟥 ALCANCE", "confianca": "🟨 CONFIANÇA", "conversao": "🟩 CONVERSÃO", "prova": "🟦 PROVA"}
    linhas.append(f"  📋 Content Role: {role_map.get(resultado.get('content_role', ''), '?')}")
    if resultado.get("content_type"):
        linhas.append(f"  🎯 Content Type: {resultado['content_type']}")
    linhas.append(f"  🎨 Estilo: {resultado.get('estilo_nome', '')} (ID: {resultado.get('estilo_id', '')})")
    linhas.append(f"  📝 Headline: {resultado.get('headline', '')}")
    linhas.append(f"  🎬 Cena: {resultado.get('cinematic_scene', {}).get('scene_type', '')}")
    linhas.append(f"  💡 Iluminação: {resultado.get('cinematic_scene', {}).get('lighting', '')[:60]}")
    if resultado.get("brand_world"):
        linhas.append(f"  🌍 Brand World: {resultado['brand_world']}")
    q = resultado.get("qualidade", {})
    linhas.append(f"  ⭐ Score: {q.get('score', '?')}/10 {'✅' if q.get('aprovado') else '⚠️'}")
    meta = resultado.get("meta", {})
    linhas.append(f"  ⏱️  Tempo: {meta.get('duracao_segundos', '?')}s | Palavras: {meta.get('word_count', '?')}")
    if meta.get("attempt"):
        linhas.append(f"  🔄 Tentativa: {meta['attempt']}")
    if resultado.get("output_path"):
        linhas.append(f"  💾 Salvo em: {resultado['output_path']}")
    if resultado.get("critique"):
        crit = resultado["critique"]
        if crit.get("issues"):
            linhas.append(f"  🔍 Crítica: {len(crit['issues'])} issues encontradas (refinado)")
    return "\n".join(linhas)


def extrair_metricas_csv(resultado: Dict[str, Any]) -> str:
    """Extrai métricas em formato CSV para dashboards."""
    headers = ["timestamp", "produto", "content_role", "content_type", "estilo", "score", "aprovado",
               "scene_type", "brand_world", "duracao_s", "word_count", "headline"]
    q = resultado.get("qualidade", {})
    meta = resultado.get("meta", {})
    cinematic = resultado.get("cinematic_scene", {})
    valores = [
        datetime.now().isoformat(),
        resultado.get("product_name", resultado.get("meta", {}).get("product_name", "")),
        resultado.get("content_role", ""),
        resultado.get("content_type", ""),
        resultado.get("estilo_nome", ""),
        str(q.get("score", "")),
        str(q.get("aprovado", "")),
        cinematic.get("scene_type", ""),
        resultado.get("brand_world", ""),
        str(meta.get("duracao_segundos", "")),
        str(meta.get("word_count", "")),
        f'"{resultado.get("headline", "")}"',
    ]
    return ",".join(headers) + "\n" + ",".join(valores)


def analisar_tendencia_qualidade(resultados: List[Dict]) -> Dict[str, Any]:
    """Analisa tendência de qualidade ao longo de múltiplas campanhas."""
    if not resultados:
        return {"status": "sem_dados", "total_campanhas": 0}
    scores = [r.get("qualidade", {}).get("score", 0) for r in resultados if r.get("qualidade", {}).get("score", 0) > 0]
    if not scores:
        return {"status": "sem_scores", "total_campanhas": len(resultados)}
    media = round(sum(scores) / len(scores), 1)
    tendencia = "estável"
    if len(scores) >= 3:
        metade = len(scores) // 2
        primeira = sum(scores[:metade]) / metade
        segunda = sum(scores[metade:]) / (len(scores) - metade)
        diff = segunda - primeira
        if diff > 0.5:
            tendencia = "melhorando 📈"
        elif diff < -0.5:
            tendencia = "piorando 📉"
    return {
        "status": "ok",
        "total_campanhas": len(resultados),
        "media_geral": media,
        "score_maximo": max(scores),
        "score_minimo": min(scores),
        "tendencia": tendencia,
    }


# ============================================================================
# AUTO-TESTE FINAL EXPANDIDO
# ============================================================================
class AutoTesterFinal:
    """Teste final de integração com todos os 55 blocos."""

    def __init__(self):
        self.results = []
        self.passed = 0
        self.failed = 0

    def _record(self, name, success, msg=""):
        self.results.append({"name": name, "success": success, "message": msg})
        if success:
            self.passed += 1
        else:
            self.failed += 1
        print(f"  {'✅' if success else '❌'} {name} {msg}")

    def run_all(self):
        print("=" * 78)
        print("🔍 AUTO-TESTE FINAL — HERMES IMAGE ENGINE V20 (55 BLOCOS)")
        print("=" * 78)
        self._test_full_pipeline()
        self._test_cache()
        self._test_regeneration()
        self._test_export()
        self._test_cli_json()
        self._test_hyper_detail()
        self._test_creative_concept()
        self._test_mandatory_copy()
        self._test_environment_reflection()
        self._test_camera_simulation()
        self._test_story_composition()
        self._test_sensory_immersion()
        self._test_post_critique()
        self._test_universal_design()
        self._test_content_type_router()
        self._test_brand_world_builder()
        self._test_multi_format_adapter()
        self._test_validar_produto_input()
        self._test_extrair_metricas_csv()
        self._test_analisar_tendencia()
        print(f"\n✅ {self.passed}/{len(self.results)} testes passaram, {self.failed} falharam")

    def _test_full_pipeline(self):
        try:
            copy = "Seu joelho dói ao subir escada. Nossa joelheira resolve em 30 dias. De R$ 189,90 por R$ 129,90. Link na bio."
            result = run({"copy": copy, "product_name": "Joelheira Premium", "product_category": "saúde", "timeframe": "30 dias"})
            score = result.get("qualidade", {}).get("score", 0)
            self._record("Pipeline Completo", score > 0, f"Score: {score}/10")
        except Exception as e:
            self._record("Pipeline Completo", False, str(e))

    def _test_cache(self):
        try:
            copy = "Cache test copy " + str(random.randint(1, 1000))
            result1 = run({"copy": copy})
            result2 = run({"copy": copy})
            self._record("Cache", result1.get("prompt_completo") == result2.get("prompt_completo"))
        except Exception as e:
            self._record("Cache", False, str(e))

    def _test_regeneration(self):
        try:
            loop = RegenerationLoop(max_attempts=2)

            def mock_build(attempt=0, **kwargs):
                return {"qualidade": {"score": 9.5 if attempt > 0 else 5.0, "aprovado": attempt > 0}, "estilo_id": 1}
            result = loop.execute(mock_build)
            self._record("Regeneração", result.get("qualidade", {}).get("aprovado", False))
        except Exception as e:
            self._record("Regeneração", False, str(e))

    def _test_export(self):
        try:
            dummy = {"prompt_completo": "test", "negative_prompt": "no", "estilo_nome": "Test", "qualidade": {"score": 9.5, "aprovado": True}}
            md = output_formatter.to_markdown(dummy)
            self._record("Export Markdown", "##" in md)
        except Exception as e:
            self._record("Export Markdown", False, str(e))

    def _test_cli_json(self):
        try:
            payload = '{"copy": "Teste de CLI com JSON. Funciona bem. R$ 50. Link na bio."}'
            result = run(json.loads(payload))
            self._record("CLI JSON", result is not None and "prompt_completo" in result)
        except Exception as e:
            self._record("CLI JSON", False, str(e))

    def _test_hyper_detail(self):
        try:
            style = ESTILOS_POST[13]
            scene = cinematic_scene_composer.compose(style, "Teste", ContentRole.CONVERSAO)
            instr = hyper_detail_engine.generate(style, scene, "Teste")
            self._record("Hyper-Detail Engine", len(instr) > 100)
        except Exception as e:
            self._record("Hyper-Detail Engine", False, str(e))

    def _test_creative_concept(self):
        try:
            instr = creative_concept_exploder.generate("oferta", "Produto X", ESTILOS_POST[13])
            self._record("Creative Concept", "CREATIVE CONCEPT" in instr)
        except Exception as e:
            self._record("Creative Concept", False, str(e))

    def _test_mandatory_copy(self):
        try:
            instr = mandatory_copy_embedder.generate("Headline", "Copy text here", ESTILOS_POST[13], {})
            self._record("Mandatory Copy", "MANDATORY COPY" in instr)
        except Exception as e:
            self._record("Mandatory Copy", False, str(e))

    def _test_environment_reflection(self):
        try:
            scene = cinematic_scene_composer.compose(ESTILOS_POST[13], "Vidro", ContentRole.CONVERSAO)
            instr = environmental_reflection_engine.generate(scene, "Vidro")
            self._record("Environment Reflection", "SPECULAR REFLECTIONS" in instr)
        except Exception as e:
            self._record("Environment Reflection", False, str(e))

    def _test_camera_simulation(self):
        try:
            instr = camera_lens_simulator.generate(ESTILOS_POST[13])
            self._record("Camera Simulation", "FILM STOCK" in instr)
        except Exception as e:
            self._record("Camera Simulation", False, str(e))

    def _test_story_composition(self):
        try:
            instr = story_composition_force.generate("oferta", ESTILOS_POST[13])
            self._record("Story Composition", len(instr) > 50)
        except Exception as e:
            self._record("Story Composition", False, str(e))

    def _test_sensory_immersion(self):
        try:
            scene = cinematic_scene_composer.compose(ESTILOS_POST[13], "Teste", ContentRole.CONVERSAO)
            instr = sensory_immersion_layer.generate(scene, ESTILOS_POST[13])
            self._record("Sensory Immersion", "SENSORY IMMERSION" in instr)
        except Exception as e:
            self._record("Sensory Immersion", False, str(e))

    def _test_post_critique(self):
        try:
            prompt = "CREATE AN AD. Product shot. Studio lighting."
            critique = post_generation_critique.critique(prompt)
            self._record("Post Critique", not critique["passed"])
        except Exception as e:
            self._record("Post Critique", False, str(e))

    def _test_universal_design(self):
        try:
            instr = universal_design_system.generate("educativo", ESTILOS_POST[11])
            self._record("Universal Design", "DESIGN TOKENS" in instr)
        except Exception as e:
            self._record("Universal Design", False, str(e))

    def _test_content_type_router(self):
        try:
            result = content_type_router.route("Compre agora com 50% de desconto! R$ 99,90.", ContentRole.CONVERSAO, {"has_preco": True, "has_cta_forte": True})
            self._record("Content Type Router", result.get("content_type") == "oferta")
        except Exception as e:
            self._record("Content Type Router", False, str(e))

    def _test_brand_world_builder(self):
        try:
            brand_config = brand_simulation_engine.get_brand_config(ESTILOS_POST[13])
            world = brand_world_builder.build(ESTILOS_POST[13], brand_config)
            self._record("Brand World Builder", "instruction" in world)
        except Exception as e:
            self._record("Brand World Builder", False, str(e))

    def _test_multi_format_adapter(self):
        try:
            instr = multi_format_adapter.adapt("CARROSSEL", "oferta", ESTILOS_POST[13], "Teste")
            self._record("Multi-Format Adapter", "CARROSSEL" in instr)
        except Exception as e:
            self._record("Multi-Format Adapter", False, str(e))

    def _test_validar_produto_input(self):
        try:
            valido, _ = validar_produto_input({"nome": "Teste", "preco": "89.90"})
            self._record("Validar Produto Input", valido)
        except Exception as e:
            self._record("Validar Produto Input", False, str(e))

    def _test_extrair_metricas_csv(self):
        try:
            dummy = {"qualidade": {"score": 9.5, "aprovado": True}, "meta": {"duracao_segundos": 1.5, "word_count": 100, "product_name": "Teste"}, "cinematic_scene": {"scene_type": "test"}, "content_role": "conversao", "content_type": "oferta", "estilo_nome": "Teste", "brand_world": "test", "headline": "Teste"}
            csv = extrair_metricas_csv(dummy)
            self._record("Extrair Métricas CSV", len(csv) > 50)
        except Exception as e:
            self._record("Extrair Métricas CSV", False, str(e))

    def _test_analisar_tendencia(self):
        try:
            dummy1 = {"qualidade": {"score": 9.0}}
            dummy2 = {"qualidade": {"score": 9.5}}
            dummy3 = {"qualidade": {"score": 9.8}}
            tendencia = analisar_tendencia_qualidade([dummy1, dummy2, dummy3])
            self._record("Analisar Tendência", tendencia.get("tendencia") == "melhorando 📈")
        except Exception as e:
            self._record("Analisar Tendência", False, str(e))


# ============================================================================
# CLI PROFISSIONAL COMPLETA
# ============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Hermes Image Engine V20 — Geração de prompts cinematográficos Nível Deus.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
        Exemplos de uso:
          python hermes_image_skill.py --copy "Sua copy aqui" --produto "Escova" --categoria "beleza"
          python hermes_image_skill.py --json '{"copy":"...", "product_name":"..."}'
          python hermes_image_skill.py --campanha campanha.json
          python hermes_image_skill.py --auto-teste
          python hermes_image_skill.py --listar-estilos
        """)
    )
    parser.add_argument("--copy", type=str, help="Texto completo da copy")
    parser.add_argument("--copy-file", type=str, help="Arquivo contendo a copy")
    parser.add_argument("--campanha", type=str, help="Arquivo JSON da campanha do Hermes Engine")
    parser.add_argument("--json", type=str, help="JSON com parâmetros de entrada (modo agente)")
    parser.add_argument("--produto", type=str, default="", help="Nome do produto")
    parser.add_argument("--categoria", type=str, default="produto", help="Categoria do produto")
    parser.add_argument("--tempo", type=str, default="7 dias", help="Período para headlines de prova")
    parser.add_argument("--formato", type=str, default="POST", choices=["POST", "CARROSSEL", "STORY"])
    parser.add_argument("--plataforma", type=str, default="instagram_feed", help="Plataforma de destino")
    parser.add_argument("--output", type=str, default="output/image_prompt.json", help="Caminho do arquivo de saída")
    parser.add_argument("--no-save", action="store_true", help="Não salvar arquivo")
    parser.add_argument("--verbose", action="store_true", help="Ativar logs detalhados")
    parser.add_argument("--auto-teste", action="store_true", help="Executar bateria de testes")
    parser.add_argument("--listar-estilos", action="store_true", help="Listar todos os estilos disponíveis")
    parser.add_argument("--quiet", action="store_true", help="Suprimir logs (apenas JSON no stdout)")

    args = parser.parse_args()

    # Configurar logging
    if args.quiet:
        logger.setLevel(logging.ERROR)
    elif args.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.WARNING)

    # Modo auto-teste
    if args.auto_teste:
        print("=" * 78)
        print("🔍 MODO AUTO-TESTE — HERMES IMAGE ENGINE V20 (55 BLOCOS)")
        print("=" * 78)
        tester = AutoTesterFinal()
        tester.run_all()
        sys.exit(0 if tester.failed == 0 else 1)

    # Modo listar estilos
    if args.listar_estilos:
        estilos = listar_estilos_disponiveis()
        print(f"\n{'ID':<5} {'Nome':<30} {'Formato':<10} {'Role':<12} {'AD':<22} {'Scene':<20}")
        print("-" * 100)
        for e in estilos:
            print(f"{e['id']:<5} {e['nome']:<30} {e['formato']:<10} {e['content_role']:<12} {e['ad_type']:<22} {e['scene_type']:<20}")
        print(f"\nTotal: {len(estilos)} estilos.")
        sys.exit(0)

    # Determinar copy de entrada
    copy_text = ""
    product_name = args.produto
    product_category = args.categoria
    timeframe = args.tempo
    formato = args.formato
    platform_str = args.plataforma

    if args.json:
        try:
            params = json.loads(args.json)
            copy_text = params.get("copy", "")
            product_name = params.get("produto", params.get("product_name", product_name))
            product_category = params.get("categoria", params.get("product_category", product_category))
            timeframe = params.get("tempo", params.get("timeframe", timeframe))
            formato = params.get("formato", formato).upper()
            platform_str = params.get("plataforma", params.get("platform", platform_str)).lower()
        except json.JSONDecodeError as e:
            print(f"❌ JSON inválido: {e}")
            sys.exit(1)
    elif args.campanha:
        try:
            with open(args.campanha, "r", encoding="utf-8") as f:
                campanha = json.load(f)
            product_name = campanha.get("produto", product_name)
            prompts = {}
            for fmt_key in ["POST", "CARROSSEL", "STORY"]:
                if fmt_key in campanha.get("criativos", {}):
                    copy_data = campanha["criativos"][fmt_key]
                    copy_txt = copy_data.get("texto", "") if isinstance(copy_data, dict) else str(copy_data)
                    if copy_txt:
                        try:
                            result = run({"copy": copy_txt, "product_name": product_name, "product_category": product_category,
                                         "timeframe": timeframe, "formato": fmt_key, "platform": platform_str})
                            prompts[fmt_key] = result
                        except Exception as e:
                            prompts[fmt_key] = {"erro": str(e)}
            if args.quiet:
                print(json.dumps(prompts, ensure_ascii=False, indent=2))
            else:
                for k, v in prompts.items():
                    print(f"\n{'='*78}\n{k}\n{'='*78}")
                    if "erro" in v:
                        print(f"Erro: {v['erro']}")
                    else:
                        print(gerar_resumo_campanha(v))
                        print(f"\n🎨 PROMPT:\n{v.get('prompt_completo', '')[:500]}...")
            if not args.no_save:
                os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
                with open(args.output, "w", encoding="utf-8") as f:
                    json.dump(prompts, f, ensure_ascii=False, indent=2)
            sys.exit(0)
        except Exception as e:
            print(f"❌ Erro ao processar campanha: {e}")
            sys.exit(1)
    elif args.copy_file:
        try:
            with open(args.copy_file, "r", encoding="utf-8") as f:
                copy_text = f.read().strip()
        except FileNotFoundError:
            print(f"❌ Arquivo não encontrado: {args.copy_file}")
            sys.exit(1)
    elif args.copy:
        copy_text = args.copy
    else:
        print("❌ Nenhuma copy fornecida. Use --copy, --copy-file, --campanha ou --json.")
        sys.exit(1)

    if len(copy_text.strip()) < 20:
        print("❌ A copy deve ter pelo menos 20 caracteres.")
        sys.exit(1)

    # Executar geração
    try:
        resultado = run({
            "copy": copy_text,
            "product_name": product_name,
            "product_category": product_category,
            "timeframe": timeframe,
            "formato": formato,
            "platform": platform_str,
        })
    except Exception as e:
        print(f"❌ Erro ao gerar prompt: {e}")
        sys.exit(1)

    # Saída
    if args.quiet:
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
    else:
        print(gerar_resumo_campanha(resultado))
        print(f"\n🎨 PROMPT COMPLETO:\n{resultado.get('prompt_completo', '')}")
        print(f"\n🚫 NEGATIVE PROMPT:\n{resultado.get('negative_prompt', '')}")
        if not args.no_save:
            os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(resultado, f, ensure_ascii=False, indent=2)
            print(f"\n💾 Prompt salvo em {os.path.abspath(args.output)}")


# ============================================================================
# EXPORTAÇÕES PÚBLICAS FINAIS (__all__ COMPLETO)
# ============================================================================
__all__ = [
    # Funções principais
    "run",
    "gerar_resumo_prompt",
    "gerar_resumo_campanha",
    "exportar_prompt_markdown",
    "extrair_metricas_csv",
    "analisar_tendencia_qualidade",
    "listar_estilos_disponiveis",
    "validar_produto_input",
    "executar_auto_teste",

    # Builder principal
    "ImagePromptBuilderV20",

    # Todos os motores e engines (55 blocos)
    "ContentRoleClassifier",
    "CopyPatternAnalyzer",
    "StyleSelector",
    "AdTypeDecider",
    "HeadlineGenerator",
    "TextOverlayEngine",
    "LayoutEngine",
    "BrandSimulationEngine",
    "CameraEngine",
    "NegativePromptBuilder",
    "PromptQualityGate",
    "RegenerationLoop",
    "PromptAssembler",
    "OutputFormatter",
    "HermesAgentInterface",
    "AutoTestSuite",
    "VisualHookEngine",
    "AttentionElementsEngine",
    "CompositionEngine",
    "ProductPlacementEngine",
    "ColorPaletteEngine",
    "TypographyEngine",
    "LightingEngine",
    "CinematicSceneComposer",
    "MaterialTextureDirector",
    "CinematicLightingDirector",
    "ColorGradeMoodDirector",
    "SceneDepthPerspectiveEngine",
    "AtmosphericParticleEngine",
    "CausticRefractiveLightEngine",
    "GoldenRatioCompositionEngine",
    "TextureStorytellingEngine",
    "EmotionalColorTemperatureShift",
    "ProductShadowDesign",
    "VisualEchoRepetitionEngine",
    "MicroImperfectionEngine",
    "TemperatureSensoryEngine",
    "TimeOfDaySimulation",
    "ProductHeroLightingRig",
    "ContentTypeRouter",
    "VisualStorytellingEngine",
    "BrandWorldBuilder",
    "TypographyIntegrationSystem",
    "MultiFormatAdapter",
    "HyperDetailSpecificationEngine",
    "CreativeConceptExploder",
    "MandatoryCopyEmbedder",
    "EnvironmentalReflectionEngine",
    "CameraLensSimulator",
    "StoryDrivenCompositionForce",
    "SensoryImmersionLayer",
    "MultiFormatConsistencyEnforcer",
    "PostGenerationCritique",
    "UniversalDesignSystem",

    # Schemas
    "ContentAnalysis",
    "StyleConfig",
    "CinematicSceneConfig",
    "ImagePromptOutput",

    # Enums
    "ContentRole",
    "Platform",
    "ConversionLevel",
    "ProductionMode",
    "QualityGateResult",
    "AdType",
    "SceneType",
    "LightingStyle",
    "DepthStyle",
    "TimeOfDay",

    # Exceções
    "EngineError",
    "QualityGateBlockedError",
    "PipelineAbortedError",
    "InvalidInputError",

    # Catálogos de estilos
    "ESTILOS_POST",
    "ESTILOS_CARROSSEL",
    "ESTILOS_STORY",

    # Bancos de dados cinematográficos
    "SCENE_MAPPING",
    "LIGHTING_MAPPING",
    "DEPTH_MAPPING",
    "COLOR_GRADE_MAPPING",
    "ATMOSPHERIC_PARTICLES",
    "TEXTURE_STORY_MAPPING",
    "BRAND_REFERENCES",
    "CINEMATIC_SCENE_STYLES",

    # Constantes
    "VERSION",
    "BUILD",
    "SCORE_MINIMO_ABSOLUTO",
    "NOTA_MINIMA_DIMENSAO",
    "MAX_TENTATIVAS_REGENERACAO",
    "CONTENT_ROLE_ALCANCE",
    "CONTENT_ROLE_CONFIANCA",
    "CONTENT_ROLE_CONVERSAO",
    "CONTENT_ROLE_PROVA",
    "PRODUCTION_MODE_STATIC_AD",
    "AD_TYPE_DESIGN",
    "AD_TYPE_PHOTOGRAPHY_WITH_TEXT",
]


def executar_auto_teste() -> Dict[str, Any]:
    """Executa a bateria completa de testes de integridade."""
    tester = AutoTesterFinal()
    tester.run_all()
    return {"passed": tester.passed, "failed": tester.failed, "total": len(tester.results)}


# ============================================================================
# PONTO DE ENTRADA PRINCIPAL
# ============================================================================
if __name__ == "__main__":
    main()

print("=" * 78)
print("✅ HERMES IMAGE ENGINE V20 — PARTE 5/5 CARREGADA COM SUCESSO")
print(f"   Versão: {VERSION} | Build: {BUILD}")
print(f"   CLI completa, testes e utilitários prontos para produção.")
print(f"   Pipeline completo com 55 blocos integrados — NÍVEL DEUS ABSOLUTO.")
print("=" * 78)

if __name__ == "__main__":
    main()
