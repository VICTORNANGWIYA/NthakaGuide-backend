

PEST_DISEASE_RISKS = {

    "maize": [
        {
            "name":          "Fall Armyworm (FAW)",
            "type":          "pest",
            "trigger_rain":  ["Moderate", "High", "Very High"],
            "trigger_temp":  (22, 35),
            "trigger_humid": 70,
            "risk_level":    "high",
            "symptoms":      "Ragged leaf damage, frass in whorl, defoliation of young plants",
            "action":        (
                "Scout fields twice a week. Apply Coragen (chlorantraniliprole) "
                "or Ampligo at first sign. Push-pull intercropping with Desmodium "
                "reduces FAW pressure. Early planting avoids peak FAW season."
            ),
        },
        {
            "name":          "Maize Streak Virus (MSV)",
            "type":          "disease",
            "trigger_rain":  ["Low", "Very Low"],
            "trigger_temp":  (25, 38),
            "trigger_humid": 50,
            "risk_level":    "medium",
            "symptoms":      "Yellow streaking on leaves, stunted growth, poor cob development",
            "action":        (
                "Use MSV-tolerant hybrids (SC403, DK8033). Control leafhopper "
                "vector with seed dressing (imidacloprid). Early planting "
                "reduces exposure to peak leafhopper populations."
            ),
        },
        {
            "name":          "Grey Leaf Spot (GLS)",
            "type":          "disease",
            "trigger_rain":  ["High", "Very High"],
            "trigger_temp":  (20, 30),
            "trigger_humid": 80,
            "risk_level":    "medium",
            "symptoms":      "Rectangular grey-tan lesions with yellow halos on lower leaves",
            "action":        (
                "Rotate maize with legumes every 2 years. Use GLS-tolerant "
                "varieties. Avoid dense planting which increases humidity. "
                "Foliar fungicides (mancozeb) effective if applied early."
            ),
        },
    ],

    "rice": [
        {
            "name":          "Rice Blast",
            "type":          "disease",
            "trigger_rain":  ["High", "Very High"],
            "trigger_temp":  (20, 30),
            "trigger_humid": 85,
            "risk_level":    "high",
            "symptoms":      "Diamond-shaped lesions on leaves and neck; whitehead panicles",
            "action":        (
                "Use blast-resistant varieties (Kilombero, Faya). Apply "
                "tricyclazole fungicide at booting stage. Avoid excess nitrogen "
                "which increases susceptibility. Drain fields periodically."
            ),
        },
        {
            "name":          "Brown Planthopper (BPH)",
            "type":          "pest",
            "trigger_rain":  ["High", "Very High"],
            "trigger_temp":  (24, 35),
            "trigger_humid": 80,
            "risk_level":    "medium",
            "symptoms":      "Yellowing in circular patches (hopperburn), plants lodging",
            "action":        (
                "Monitor with sticky traps. Apply buprofezin at early instar. "
                "Avoid excessive nitrogen. Drain fields to disrupt BPH habitat. "
                "Encourage natural enemies by avoiding broad-spectrum insecticides."
            ),
        },
        {
            "name":          "Bacterial Leaf Blight (BLB)",
            "type":          "disease",
            "trigger_rain":  ["Very High"],
            "trigger_temp":  (25, 35),
            "trigger_humid": 90,
            "risk_level":    "medium",
            "symptoms":      "Water-soaked leaf margins turning yellow then white from tip",
            "action":        (
                "Use certified disease-free seed. Avoid flood damage which "
                "creates entry wounds. Copper-based bactericides reduce spread. "
                "Remove and burn infected plant debris after harvest."
            ),
        },
    ],

    "soybean": [
        {
            "name":          "Soybean Rust",
            "type":          "disease",
            "trigger_rain":  ["High", "Very High"],
            "trigger_temp":  (15, 28),
            "trigger_humid": 75,
            "risk_level":    "high",
            "symptoms":      "Tan-grey pustules on leaf undersides, premature defoliation",
            "action":        (
                "Apply triazole fungicide (tebuconazole) at R1 growth stage. "
                "Scout fields every 2 weeks after flowering. Early planting "
                "avoids peak rust season. Use early-maturing varieties."
            ),
        },
        {
            "name":          "Soybean Aphids",
            "type":          "pest",
            "trigger_rain":  ["Low", "Very Low"],
            "trigger_temp":  (20, 30),
            "trigger_humid": 55,
            "risk_level":    "medium",
            "symptoms":      "Yellowing, leaf curl, sticky honeydew on leaves",
            "action":        (
                "Monitor from V2 stage. Encourage natural enemies (ladybirds). "
                "Apply imidacloprid if population exceeds economic threshold. "
                "Avoid water stress which makes plants more susceptible."
            ),
        },
    ],

    "groundnut": [
        {
            "name":          "Groundnut Rosette Virus",
            "type":          "disease",
            "trigger_rain":  ["Low", "Very Low", "Moderate"],
            "trigger_temp":  (25, 35),
            "trigger_humid": 60,
            "risk_level":    "high",
            "symptoms":      "Severe stunting, small chlorotic leaves, bushy rosette appearance",
            "action":        (
                "Use rosette-resistant varieties (ICGV, Chalimbana). "
                "Apply mineral oil spray to repel aphid vector. "
                "Plant at recommended density to form canopy quickly. "
                "Early planting and border crops reduce aphid incursion."
            ),
        },
        {
            "name":          "Leaf Spot (Cercospora)",
            "type":          "disease",
            "trigger_rain":  ["High", "Very High"],
            "trigger_temp":  (20, 30),
            "trigger_humid": 80,
            "risk_level":    "medium",
            "symptoms":      "Dark brown circular spots with yellow halo on leaves",
            "action":        (
                "Apply mancozeb or chlorothalonil starting at 30 days after planting. "
                "Rotate groundnut with cereals. Remove and bury crop debris. "
                "Avoid overhead irrigation that wets foliage."
            ),
        },
    ],

    "cassava": [
        {
            "name":          "Cassava Mosaic Disease (CMD)",
            "type":          "disease",
            "trigger_rain":  ["Low", "Moderate"],
            "trigger_temp":  (25, 35),
            "trigger_humid": 60,
            "risk_level":    "high",
            "symptoms":      "Mosaic leaf discolouration, leaf distortion, stunted growth",
            "action":        (
                "Use CMD-resistant varieties (Mkondezi, Sauti). "
                "Always plant clean stem cuttings from disease-free plants. "
                "Remove and destroy infected plants immediately. "
                "Control whitefly vector with yellow sticky traps."
            ),
        },
        {
            "name":          "Cassava Brown Streak Disease (CBSD)",
            "type":          "disease",
            "trigger_rain":  ["Moderate", "High"],
            "trigger_temp":  (20, 30),
            "trigger_humid": 70,
            "risk_level":    "high",
            "symptoms":      "Brown streaking on stems, corky brown necrosis in tubers",
            "action":        (
                "Use CBSD-tolerant varieties. Never plant from infected material. "
                "CBSD spreads through infected cuttings and whitefly — both "
                "must be managed together. Report severe outbreaks to DARS."
            ),
        },
    ],

    "sweetpotato": [
        {
            "name":          "Sweet Potato Weevil",
            "type":          "pest",
            "trigger_rain":  ["Low", "Very Low"],
            "trigger_temp":  (25, 38),
            "trigger_humid": 50,
            "risk_level":    "high",
            "symptoms":      "Pin-holes in vines and tubers, tunnelling damage in stored roots",
            "action":        (
                "Use healthy, certified planting material. "
                "Hill soil around vines to prevent vine-to-soil cracks. "
                "Harvest promptly — do not leave tubers in ground. "
                "Pheromone traps can monitor adult weevil populations."
            ),
        },
        {
            "name":          "Sweet Potato Virus Disease (SPVD)",
            "type":          "disease",
            "trigger_rain":  ["Moderate", "High"],
            "trigger_temp":  (22, 30),
            "trigger_humid": 70,
            "risk_level":    "medium",
            "symptoms":      "Severe leaf distortion, chlorosis, greatly reduced yield",
            "action":        (
                "Plant certified virus-free vine cuttings. Use resistant varieties. "
                "Control aphid and whitefly vectors. Rogue out infected plants early. "
                "Replant clean cuttings from DARS-approved sources."
            ),
        },
    ],

    "beans": [
        {
            "name":          "Bean Fly (Ophiomyia)",
            "type":          "pest",
            "trigger_rain":  ["Moderate", "High"],
            "trigger_temp":  (18, 28),
            "trigger_humid": 75,
            "risk_level":    "high",
            "symptoms":      "Yellowing seedlings, swollen stem base, maggot tunnels",
            "action":        (
                "Apply imidacloprid seed dressing before planting. "
                "Early planting in warm soil reduces seedling vulnerability. "
                "Destroy crop residues after harvest to break pest cycle. "
                "Intercropping with maize reduces bean fly pressure."
            ),
        },
        {
            "name":          "Angular Leaf Spot (ALS)",
            "type":          "disease",
            "trigger_rain":  ["High", "Very High"],
            "trigger_temp":  (16, 28),
            "trigger_humid": 80,
            "risk_level":    "medium",
            "symptoms":      "Angular water-soaked spots limited by leaf veins, grey undersurface",
            "action":        (
                "Use ALS-resistant varieties. Apply mancozeb at 7-day intervals. "
                "Avoid overhead irrigation. Remove infected plant debris. "
                "Rotate beans with non-legumes every 2 seasons."
            ),
        },
    ],

    "cotton": [
        {
            "name":          "Bollworm (Helicoverpa armigera)",
            "type":          "pest",
            "trigger_rain":  ["Moderate", "High"],
            "trigger_temp":  (25, 38),
            "trigger_humid": 65,
            "risk_level":    "high",
            "symptoms":      "Bored bolls with entry holes, frass around damaged squares and bolls",
            "action":        (
                "Apply cypermethrin at square formation. Scout twice weekly "
                "from flowering. Avoid excessive nitrogen which produces "
                "lush canopy attractive to moths. Use Bt cotton if available."
            ),
        },
        {
            "name":          "Cotton Aphid",
            "type":          "pest",
            "trigger_rain":  ["Low", "Very Low"],
            "trigger_temp":  (20, 30),
            "trigger_humid": 55,
            "risk_level":    "medium",
            "symptoms":      "Curled leaves, honeydew, sooty mould on leaves",
            "action":        (
                "Encourage natural enemies (parasitic wasps, lacewings). "
                "Apply imidacloprid only if population exceeds threshold. "
                "Avoid broad-spectrum sprays that kill natural enemies."
            ),
        },
    ],

    "tobacco": [
        {
            "name":          "Tobacco Mosaic Virus (TMV)",
            "type":          "disease",
            "trigger_rain":  ["Moderate"],
            "trigger_temp":  (18, 30),
            "trigger_humid": 65,
            "risk_level":    "medium",
            "symptoms":      "Mosaic leaf pattern, leaf distortion, stunting",
            "action":        (
                "Use TMV-resistant varieties. Wash hands with soap before "
                "handling plants. Disinfect tools with 1% bleach solution. "
                "Remove and bury infected plants immediately."
            ),
        },
        {
            "name":          "Tobacco Cutworm",
            "type":          "pest",
            "trigger_rain":  ["Moderate", "High"],
            "trigger_temp":  (15, 28),
            "trigger_humid": 70,
            "risk_level":    "high",
            "symptoms":      "Seedlings cut at soil level overnight, C-shaped larvae in soil",
            "action":        (
                "Bait with poison bran around seedbed. Hand-pick larvae at dusk. "
                "Apply chlorpyrifos drench around stem base. "
                "Deep tillage before planting exposes larvae to birds."
            ),
        },
    ],

    "banana": [
        {
            "name":          "Banana Xanthomonas Wilt (BXW)",
            "type":          "disease",
            "trigger_rain":  ["High", "Very High"],
            "trigger_temp":  (18, 30),
            "trigger_humid": 80,
            "risk_level":    "high",
            "symptoms":      "Yellowing and wilting of central leaves, oozing from cut pseudostem",
            "action":        (
                "Remove and bury all male flower buds with clean tool weekly. "
                "De-sucker: leave only one sucker per mat. "
                "Disinfect tools between plants with 2% bleach. "
                "Report BXW suspected cases to nearest agricultural office."
            ),
        },
        {
            "name":          "Banana Weevil Borer",
            "type":          "pest",
            "trigger_rain":  ["Moderate", "High"],
            "trigger_temp":  (22, 35),
            "trigger_humid": 75,
            "risk_level":    "medium",
            "symptoms":      "Tunnels in corm, yellowing, wilting, plant fall over",
            "action":        (
                "Clean planting material by removing outer corm. "
                "Place split pseudostem traps to attract and collect adults. "
                "Apply chlorpyrifos to corm at planting. "
                "Remove old pseudostem debris which harbours pupae."
            ),
        },
    ],

    "pigeonpeas": [
        {
            "name":          "Fusarium Wilt",
            "type":          "disease",
            "trigger_rain":  ["Moderate", "High"],
            "trigger_temp":  (20, 32),
            "trigger_humid": 70,
            "risk_level":    "medium",
            "symptoms":      "Sudden wilting of whole plant, brown discolouration in stem vascular tissue",
            "action":        (
                "Use wilt-resistant varieties (ICEAP series). "
                "Avoid planting pigeon peas on land with history of wilt. "
                "Long crop rotation (3+ years) reduces soil inoculum. "
                "Remove and burn infected plants."
            ),
        },
        {
            "name":          "Pod Borer (Maruca vitrata)",
            "type":          "pest",
            "trigger_rain":  ["Moderate", "High"],
            "trigger_temp":  (22, 30),
            "trigger_humid": 70,
            "risk_level":    "medium",
            "symptoms":      "Webbing on flowers and young pods, bored pods with frass",
            "action":        (
                "Apply Bt spray (Bacillus thuringiensis) at flower initiation. "
                "Scout twice weekly from flowering. Neem extract provides "
                "moderate control. Chemical: lambda-cyhalothrin if severe."
            ),
        },
    ],

    "sorghum": [
        {
            "name":          "Striga (Witchweed)",
            "type":          "pest",
            "trigger_rain":  ["Low", "Moderate"],
            "trigger_temp":  (25, 38),
            "trigger_humid": 55,
            "risk_level":    "high",
            "symptoms":      "Stunted sorghum with parasitic weed emerging near base of plants",
            "action":        (
                "Use Striga-resistant sorghum varieties. Apply IR maize (imazapyr "
                "resistant) technology where available. Hand-pull Striga before "
                "seed set. Rotate with legumes to deplete Striga seed bank."
            ),
        },
        {
            "name":          "Head Smut",
            "type":          "disease",
            "trigger_rain":  ["Low", "Moderate"],
            "trigger_temp":  (20, 30),
            "trigger_humid": 60,
            "risk_level":    "medium",
            "symptoms":      "Sorghum heads replaced by smut galls, black spore masses",
            "action":        (
                "Use smut-resistant varieties. Treat seed with thiram or mancozeb "
                "before planting. Remove and destroy smutted heads before galls "
                "burst to prevent spore spread."
            ),
        },
    ],
}
