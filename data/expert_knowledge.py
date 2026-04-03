

EXPERT_ANSWERS = {
    "maize fertilizer":
        "For maize, apply NPK (23:21:0) at planting — 200 kg/ha as basal fertilizer. Then apply Urea (46% N) at 6 weeks — 100 kg/ha as top dressing. If rainfall is high, split the Urea into two applications of 50 kg/ha each to prevent nitrogen washing away.",
    "maize planting":
        "Plant maize between late November and mid-December when rains have started well. Space plants 75 cm between rows and 25 cm between holes. Plant 2 seeds per hole at 3–5 cm depth. Thin to one plant at 2 weeks.",
    "maize disease":
        "Common maize diseases: Grey Leaf Spot (rectangular grey spots), Northern Leaf Blight (cigar-shaped lesions), Maize Streak Virus (yellow streaks). Plant resistant varieties. Rotate crops. Remove infected plant debris after harvest.",
    "fall armyworm":
        "Fall armyworm caterpillars have a distinctive Y-shaped mark on their head. They hide in leaf whorls during the day and feed at night. Apply Emamectin benzoate or Chlorpyrifos insecticide in the early morning. Check crops from seedling stage. Spray at 5-day intervals if infestation is heavy.",
    "soil ph":
        "Soil pH measures how acidic or alkaline your soil is (scale 0–14). pH 7 is neutral. Most crops grow best at pH 6.0–7.0. Below 5.5 — add agricultural lime to raise pH. Above 8.0 — add sulphur or organic matter to lower pH. Apply lime at least 2–4 weeks before planting.",
    "compost":
        "To make compost: layer plant waste, food scraps, and animal manure in a pile about 1 metre high. Keep it moist. Turn every 2 weeks. After 2–3 months it becomes dark, crumbly, and smells earthy. Apply 5–10 tonnes per hectare mixed into the top 15 cm of soil.",
    "malawi rainfall":
        "Malawi's rainy season runs from November to April. The Northern Region receives 1000–1400mm annually. Central Region receives 800–1000mm. Southern Region varies from 750mm (Nsanje) to over 1200mm (Mulanje/Nkhata Bay). Zomba receives about 1050mm on average per year.",
    "groundnut":
        "Plant groundnuts in sandy loam soil at pH 5.5–7.0. Space 30 cm × 60 cm, 5 cm deep. Apply single superphosphate at planting. Do not waterlog — they rot in wet soil. Harvest at 90–120 days when leaves turn yellow.",
    "cassava":
        "Cassava tolerates poor and sandy soil with 600–1500mm rainfall. Plant stem cuttings 1 m × 1 m. Apply NPK 100 kg/ha at planting. Common problem: Cassava Mosaic Disease — use certified disease-free cuttings. Harvest at 9–12 months.",
    "grain storage":
        "Dry grain to 12–13% moisture before storing. Use PICS hermetic bags — they seal out air and kill weevils without chemicals. Store bags on wooden pallets off the ground in a cool, dry store. Check regularly for insects or moisture. Never store grain with fertilizer or chemicals.",
    "extension officer":
        "Agricultural Development Officers (ADOs) in Malawi give free farming advice. Visit your local District Agriculture Office or ask at your nearest ADMARC depot. You can also contact DARS (Department of Agricultural Research Services) for soil testing and technical advice.",
    "rice":
        "Rice needs 1000–1500mm of water per season. Plant in flat, flooded fields. Transplant seedlings at 21 days. Apply NPK 150 kg/ha at transplanting and Urea 80 kg/ha at tillering stage. Common in Karonga, Nkhotakota, Salima.",
    "tobacco":
        "Tobacco needs well-drained loamy soil with pH 5.5–6.8. Plant in October-November. Apply NPK 150 kg/ha basal and Urea 100 kg/ha as top-dressing. Cure leaves properly — flue-cured or air-cured depending on variety. Major export crop for Malawi.",
    "soybean":
        "Soybeans fix their own nitrogen — no Urea needed. Apply NPK 100 kg/ha at planting. Inoculate seeds with rhizobium bacteria before planting. Good for crop rotation with maize. Harvest when pods are brown and dry.",
    "cotton":
        "Cotton needs 700–1300mm rainfall and well-drained soil. Plant in November. Apply NPK 150 kg/ha basal and Urea 120 kg/ha in splits. Control bollworm with recommended insecticides. Pick when bolls open fully.",
    "sweet potato":
        "Sweet potato tolerates poor soil. Plant vine cuttings on ridges 30 cm apart. Apply NPK 100 kg/ha. Harvest at 3–4 months when leaves start yellowing. Good food security crop.",
    "beans":
        "Beans fix nitrogen. Apply NPK 100 kg/ha at planting — no Urea needed. Space 10 cm × 60 cm. Harvest at 60–90 days. Common varieties: Sugar beans, Napilira. Rotate with maize.",
    "sorghum":
        "Sorghum is drought-tolerant — good for areas with 300–900mm rainfall. Plant in November-December. Apply NPK 100 kg/ha and Urea 60 kg/ha. Bird damage is common — use bird scaring. Harvest when grains are hard.",
    "millet":
        "Millet needs only 200–600mm rainfall. Very drought-tolerant. Good for Nsanje, Chikwawa, Balaka. Plant on ridges. Apply NPK 80 kg/ha. Harvest when heads droop and grains are firm.",
    "weed control":
        "Control weeds within 2–3 weeks of planting before they compete with your crop. Hand-weed or use a hoe. Mulching with grass suppresses weeds. Pre-emergence herbicides can be applied just after planting on moist soil.",
    "yellow leaves":
        "Yellow leaves on maize usually mean nitrogen deficiency. Apply Urea or CAN fertilizer as top dressing. Make sure soil is moist before applying.",
    "purple stems":
        "Purple-coloured leaves or stems indicate phosphorus deficiency. Apply TSP or DAP fertilizer. Low soil pH also locks out phosphorus — test your soil pH and add lime if below 5.5.",
    "brown edges":
        "Brown leaf edges or tips often indicate potassium deficiency or water stress. Apply Muriate of Potash (MOP) and ensure adequate irrigation or moisture.",
    "irrigation":
        "Drip irrigation saves water — best for vegetables. Furrow irrigation suits maize on ridges. Water early morning or late afternoon to reduce evaporation. For smallholders, treadle pumps are affordable for dambo (wetland) farming.",
    "crop rotation":
        "Rotate maize with legumes (beans, soybeans, groundnuts) every season. This breaks pest cycles, improves soil nitrogen, and increases yields. A good pattern: maize → soybeans → maize → groundnuts.",
}

SYSTEM_PROMPT_BASE = """You are the NthakaGuide agricultural assistant for Malawi — a COM422 Final Year Project at UNIMA.

ARCHITECTURE: You use a 3-source system:
1. ML Model (Gaussian Naive Bayes with 99.55% F1-score) for crop recommendations
2. Expert Knowledge Dataset for agriculture Q&A
3. AI reasoning for complex questions

You help farmers with:
- Soil analysis and interpretation (N, P, K, pH, moisture, organic matter)
- Crop recommendations for Malawi's 28 districts
- Fertilizer types, application rates, and timing
- Rainfall patterns and seasonal forecasting (EWMA-based)
- Pest and disease management
- Post-harvest storage and grain handling
- How to use the NthakaGuide system

NUTRIENT GUIDELINES:
- Nitrogen (N): Very Low <20, Low 20-40, Medium 40-60, High >60
- Phosphorus (P): Very Low <10, Low 10-20, Medium 20-30, High >30
- Potassium (K): Low <20, Medium 20-40, High >40
- pH: Acidic <5.5, Slightly Acidic 5.5-6.0, Optimal 6.0-7.0, Alkaline >7.5

MALAWI SPECIFIC:
- Rainy season: November–April
- Main crops: Maize, tobacco, tea, sugarcane, groundnuts, rice, cotton, soybeans
- Fertilizer types: NPK 23:21:0+4S (basal), Urea 46%N (top-dressing), CAN, TSP, DAP, MOP
- Rainfall bands: Very Low (<400mm), Low (400-650mm), Moderate (650-950mm), High (950-1400mm), Very High (>1400mm)

Keep answers concise, practical, and accessible to smallholder farmers.
Use Chichewa terms when helpful (e.g., "feteleza" for fertilizer, "chimanga" for maize).
If asked about non-agriculture topics, politely redirect to farming."""


def get_expert_context(user_message: str) -> str:
    """Find the best matching expert answer for the user's question."""
    q = user_message.lower()
    for topic, answer in EXPERT_ANSWERS.items():
        topic_words = topic.split()
        match_count = sum(1 for w in topic_words if w in q)
        if match_count >= len(topic_words) or (len(topic_words) > 1 and match_count >= 1 and topic_words[0] in q):
            return f'\n\nExpert knowledge on "{topic}": {answer}'
    return ""
