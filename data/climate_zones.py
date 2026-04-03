
CLIMATE_ZONES = {
    
    "Zomba":      "high_rainfall",
    "Mulanje":    "high_rainfall",
    "Thyolo":     "high_rainfall",
    "Chiradzulu": "high_rainfall",
    "Phalombe":   "high_rainfall",
    "Nkhata Bay": "high_rainfall",   

    "Lilongwe":   "central_plateau",
    "Kasungu":    "central_plateau",
    "Dedza":      "central_plateau",
    "Ntcheu":     "central_plateau",
    "Dowa":       "central_plateau",
    "Ntchisi":    "central_plateau",
    "Mchinji":    "central_plateau",
    "Balaka":     "central_plateau",
    "Blantyre":   "central_plateau",
    "Mangochi":   "central_plateau",
    "Mwanza":     "central_plateau",

    "Karonga":    "lakeshore",
    "Salima":     "lakeshore",
    "Nkhotakota": "lakeshore",
    "Machinga":   "lakeshore",
    "Nsanje":     "lakeshore",
    "Chikwawa":   "lakeshore",

    "Mzuzu":      "northern_highlands",
    "Rumphi":     "northern_highlands",
    "Chitipa":    "northern_highlands",
    "Mzimba":     "northern_highlands",

    "Shire Valley": "shire_valley", 
}




ZONE_CROPS = {

    
    "high_rainfall": [
        "maize",
        "rice",
        "banana",
        "coffee",
        "tea",
        "pigeonpeas",
        "blackgram",
        "mungbean",
        "beans",
        "soybean",
        "sweetpotato",
        "cassava",
        "groundnuts",
        "tobacco",
        "sunflower",
        "tomato",
        "cabbage",
    ],

    
    "central_plateau": [
        "maize",
        "cassava",
        "sweetpotato",
        "groundnuts",
        "cotton",
        "tobacco",
        "soybean",
        "beans",
        "pigeonpeas",
        "chickpea",
        "kidneybeans",
        "lentil",
        "blackgram",
        "mungbean",
        "coffee",
        "sunflower",
        "sorghum",
        "millet",
        "tomato",
        "onion",
        "cabbage",
    ],

 
    "lakeshore": [
        "maize",
        "rice",
        "cotton",
        "banana",
        "coconut",
        "pigeonpeas",
        "mungbean",
        "sorghum",
        "millet",
        "cassava",
        "sweetpotato",
        "groundnuts",
        "tobacco",
        "sugarcane",   
        "beans",
        "blackgram",
    ],

   
    "northern_highlands": [
        "maize",
        "coffee",
        "banana",
        "pigeonpeas",
        "kidneybeans",
        "blackgram",
        "mungbean",
        "chickpea",
        "beans",
        "groundnuts",
        "sweetpotato",
        "cassava",
        "tobacco",
        "millet",      
        "sorghum",
        "soybean",
        "sunflower",
        "rice",
    ],

   
    "shire_valley": [
        "sorghum",
        "millet",
        "cotton",
        "maize",
        "rice",
        "cassava",
        "sweetpotato",
        "pigeonpeas",
        "groundnuts",
        "cowpea",
        "beans",
        "sesame",      
        "tobacco",
    ],
}



DEFAULT_ZONE = "central_plateau"



ZONE_DESCRIPTIONS = {
    "high_rainfall": (
        "High Rainfall Zone (1000–1500mm/yr) — tea, coffee and banana belt. "
        "Includes Mulanje, Thyolo, Zomba, Chiradzulu, Nkhata Bay."
    ),
    "central_plateau": (
        "Central Plateau (800–1100mm/yr) — maize, cotton and legume belt. "
        "Includes Lilongwe, Kasungu, Dedza, Ntcheu, Dowa, Blantyre."
    ),
    "lakeshore": (
        "Lakeshore / Lowland (600–1000mm/yr) — rice, cotton and coconut zone. "
        "Includes Salima, Nkhotakota, Machinga, Chikwawa, Nsanje, Karonga."
    ),
    "northern_highlands": (
        "Northern Highlands (900–1400mm/yr) — coffee, finger millet and bean region. "
        "Includes Mzuzu, Mzimba, Rumphi, Chitipa."
    ),
    "shire_valley": (
        "Shire Valley (400–800mm/yr) — drought-tolerant crops. "
        "Sorghum, millet, cotton, sesame. Lowest rainfall in Malawi."
    ),
}