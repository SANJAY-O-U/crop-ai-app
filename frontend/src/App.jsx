import { useState, useCallback, useRef, useEffect } from "react";
import "./index.css";

// ─── MEDICINE CATALOG ─────────────────────────────────────────────────────────
const MEDICINES = [
  {
    id:"m01", name:"Mancozeb 75% WP", brand:"Dithane M-45", company:"Dow AgroSciences",
    category:"Fungicide", type:"chemical", price:220, mrp:280, unit:"250g",
    rating:4.6, reviews:1284, badge:"BESTSELLER", badgeColor:"#2d7a31", emoji:"🟡",
    diseases:["Leaf Blight","Early Blight","Late Blight","Spot","Brown Spot","Cordana Leaf Spot","Leaf Spot","Purple Blotch"],
    crops:["tomato","potato","pepper","banana","cotton","onion","rice","wheat"],
    dosage:"2.5 g/L water", frequency:"Every 7–10 days",
    description:"Broad-spectrum protective fungicide. Controls early & late blight, leaf spots. Mix with water and spray on foliage.",
    featured:true, inStock:true, effectiveness:92,
    tags:["broad-spectrum","preventive","budget"],
    activeIngredient:"Mancozeb 75%", formulation:"WP (Wettable Powder)",
    phi:"3 days", safetyLevel:"Moderate"
  },
  {
    id:"m02", name:"Propiconazole 25% EC", brand:"Tilt 250 EC", company:"Syngenta",
    category:"Fungicide", type:"chemical", price:480, mrp:520, unit:"100 ml",
    rating:4.8, reviews:876, badge:"TOP RATED", badgeColor:"#1e5c21", emoji:"🔵",
    diseases:["Rust","Leaf Blight","Spot","Brown Rust","Yellow Rust","Sigatoka","Anthracnose","Smut"], crops:["tomato","potato","wheat","rice","banana","mango","sugarcane"],
    dosage:"1 ml/L water", frequency:"Every 14 days",
    description:"Systemic curative + protective fungicide. Highly effective against rust and blight. Absorbed through leaves.",
    featured:true, inStock:true, effectiveness:96,
    tags:["systemic","curative","rust-specialist"],
    activeIngredient:"Propiconazole 25%", formulation:"EC (Emulsifiable Concentrate)",
    phi:"7 days", safetyLevel:"Moderate"
  },
  {
    id:"m03", name:"Metalaxyl + Mancozeb", brand:"Ridomil Gold MZ", company:"Syngenta",
    category:"Fungicide", type:"chemical", price:640, mrp:720, unit:"500g",
    rating:4.7, reviews:543, badge:"LATE BLIGHT SPECIAL", badgeColor:"#dc2626", emoji:"🔴",
    diseases:["Late Blight","Early Blight","Downy Mildew"], crops:["tomato","potato","onion"],
    dosage:"2.5 g/L water", frequency:"Every 10 days",
    description:"Systemic + contact action. Gold standard for late blight and downy mildew. Metalaxyl provides internal protection with Mancozeb surface coverage.",
    featured:true, inStock:true, effectiveness:98,
    tags:["systemic","contact","late-blight","premium"],
    activeIngredient:"Metalaxyl 8% + Mancozeb 64%", formulation:"WP",
    phi:"7 days", safetyLevel:"Moderate"
  },
  {
    id:"m04", name:"Copper Oxychloride 50% WP", brand:"Blitox-50", company:"TATA Rallis",
    category:"Fungicide + Bactericide", type:"chemical", price:195, mrp:240, unit:"250g",
    rating:4.4, reviews:2108, badge:"VALUE PICK", badgeColor:"#c4923a", emoji:"🟤",
    diseases:["Bacterial Spot","Leaf Blight","Spot","Bacterial Blight","Bacterial Canker","Leaf Scald","Bacterial Leaf Blight"], crops:["tomato","potato","pepper","cotton","mango","onion","rice","sugarcane"],
    dosage:"3 g/L water", frequency:"Every 10–14 days",
    description:"Multi-purpose copper fungicide + bactericide. Controls fungal and bacterial diseases. Safe residue profile.",
    featured:false, inStock:true, effectiveness:85,
    tags:["contact","multi-disease","bacteria","budget"],
    activeIngredient:"Copper Oxychloride 50%", formulation:"WP",
    phi:"5 days", safetyLevel:"Low"
  },
  {
    id:"m05", name:"Tebuconazole 25.9% EC", brand:"Folicur EC", company:"Bayer CropScience",
    category:"Fungicide", type:"chemical", price:560, mrp:610, unit:"100 ml",
    rating:4.5, reviews:389, badge:null, badgeColor:null, emoji:"🟠",
    diseases:["Rust","Mildew","Brown Rust","Yellow Rust","Powdery Mildew"], crops:["tomato","potato","wheat","mango"],
    dosage:"1 ml/L water", frequency:"Every 14 days",
    description:"Triazole systemic fungicide. Excellent against rust, mildew and leaf spot. Long residual protection.",
    featured:false, inStock:true, effectiveness:90,
    tags:["systemic","rust","mildew","long-residual"],
    activeIngredient:"Tebuconazole 25.9%", formulation:"EC",
    phi:"7 days", safetyLevel:"Moderate"
  },
  {
    id:"m06", name:"Azoxystrobin 23% SC", brand:"Amistar", company:"Syngenta",
    category:"Fungicide", type:"chemical", price:820, mrp:950, unit:"100 ml",
    rating:4.9, reviews:712, badge:"PREMIUM", badgeColor:"#7c3aed", emoji:"🟣",
    diseases:["Early Blight","Late Blight","Spot","Mildew","Sheath Blight","Brown Spot","Anthracnose","Sigatoka"], crops:["tomato","potato","pepper","rice","wheat","mango","banana","onion"],
    dosage:"1 ml/L water", frequency:"Every 10–14 days",
    description:"Strobilurin broad-spectrum fungicide with preventive and curative action. Enhances plant health and yield.",
    featured:true, inStock:true, effectiveness:97,
    tags:["premium","broad-spectrum","yield-booster","systemic"],
    activeIngredient:"Azoxystrobin 23%", formulation:"SC (Suspension Concentrate)",
    phi:"14 days", safetyLevel:"Low"
  },
  {
    id:"m07", name:"Sulfur 80% WDG", brand:"Microthiol Disperss", company:"United Phosphorus",
    category:"Fungicide", type:"organic-approved", price:160, mrp:180, unit:"500g",
    rating:4.3, reviews:987, badge:"ORGANIC APPROVED", badgeColor:"#16a34a", emoji:"🟡",
    diseases:["Mildew","Rust","Powdery Mildew","Brown Rust","Yellow Rust","Smut"], crops:["tomato","potato","pepper","wheat","mango"],
    dosage:"3 g/L water", frequency:"Every 7–10 days",
    description:"Wettable sulfur approved for organic farming. Controls powdery mildew and rust effectively with no harmful residues.",
    featured:false, inStock:true, effectiveness:82,
    tags:["organic","mildew","rust","low-cost"],
    activeIngredient:"Sulfur 80%", formulation:"WDG",
    phi:"1 day", safetyLevel:"Low"
  },
  {
    id:"m08", name:"Neem Oil 10000 PPM", brand:"Neemazal T/S", company:"Sumitomo Chemical",
    category:"Bio-Pesticide", type:"organic", price:280, mrp:320, unit:"250 ml",
    rating:4.2, reviews:3241, badge:"100% ORGANIC", badgeColor:"#16a34a", emoji:"🌿",
    diseases:["Mildew","Spot","Leaf Blight","Sooty Mould","Banana Mosaic","Grassy Shoot","Leaf Spot"], crops:["tomato","potato","pepper","banana","cotton","mango","onion","rice","sugarcane","wheat"],
    dosage:"3 ml/L + 0.5 ml soap", frequency:"Every 5–7 days",
    description:"Cold-pressed neem oil with azadirachtin. Controls fungal diseases, insects and mites. Safe for pollinators.",
    featured:true, inStock:true, effectiveness:75,
    tags:["organic","natural","pest-control","safe"],
    activeIngredient:"Azadirachtin 0.15% + Neem Oil", formulation:"EC",
    phi:"0 days", safetyLevel:"Very Low"
  },
  {
    id:"m09", name:"Copper Hydroxide 77% WP", brand:"Kocide 3000", company:"FMC Corporation",
    category:"Bactericide + Fungicide", type:"chemical", price:410, mrp:460, unit:"250g",
    rating:4.6, reviews:521, badge:"BACTERIA SPECIALIST", badgeColor:"#0284c7", emoji:"🔵",
    diseases:["Bacterial Spot","Leaf Blight","Bacterial Canker","Bacterial Leaf Blight","Leaf Scald"], crops:["tomato","pepper","mango","rice","sugarcane"],
    dosage:"3 g/L water", frequency:"Every 7–10 days",
    description:"Premium copper bactericide. Best-in-class for bacterial spot in tomato and pepper. Low phytotoxicity.",
    featured:true, inStock:true, effectiveness:93,
    tags:["bacteria","copper","premium","pepper-specialist"],
    activeIngredient:"Copper Hydroxide 77%", formulation:"WP",
    phi:"1 day", safetyLevel:"Low"
  },
  {
    id:"m10", name:"Cymoxanil + Mancozeb", brand:"Curzate M8", company:"DuPont",
    category:"Fungicide", type:"chemical", price:380, mrp:420, unit:"250g",
    rating:4.5, reviews:298, badge:null, badgeColor:null, emoji:"⚪",
    diseases:["Late Blight","Early Blight","Downy Mildew"], crops:["tomato","potato","onion"],
    dosage:"2 g/L water", frequency:"Every 7 days",
    description:"Combination fungicide with contact + systemic action. Excellent curative + preventive late blight control.",
    featured:false, inStock:false, effectiveness:91,
    tags:["contact","systemic","late-blight"],
    activeIngredient:"Cymoxanil 8% + Mancozeb 64%", formulation:"WP",
    phi:"7 days", safetyLevel:"Moderate"
  },
  {
    id:"m11", name:"Streptomycin Sulfate 90% SP", brand:"Agrimycin-17", company:"Nufarm",
    category:"Bactericide", type:"chemical", price:320, mrp:360, unit:"100g",
    rating:4.4, reviews:176, badge:"ANTIBIOTIC", badgeColor:"#0284c7", emoji:"💉",
    diseases:["Bacterial Spot","Bacterial Blight","Bacterial Canker","Leaf Scald","Bacterial Leaf Blight"], crops:["tomato","pepper","cotton","mango","rice","sugarcane"],
    dosage:"200 ppm (0.2 g/L)", frequency:"Every 5–7 days",
    description:"Antibiotic bactericide for bacterial spot. Systemic activity. Use sparingly to prevent resistance.",
    featured:false, inStock:true, effectiveness:88,
    tags:["antibiotic","bacteria","systemic"],
    activeIngredient:"Streptomycin Sulfate 90%", formulation:"SP",
    phi:"30 days", safetyLevel:"High"
  },
  {
    id:"m12", name:"Bordeaux Mixture 2%", brand:"BordeauxMix Classic", company:"Home Blend",
    category:"Fungicide + Bactericide", type:"organic-approved", price:120, mrp:140, unit:"500g powder",
    rating:4.0, reviews:4521, badge:"DIY CLASSIC", badgeColor:"#c4923a", emoji:"🌊",
    diseases:["Leaf Blight","Spot","Bacterial Spot","Cordana Leaf Spot","Anthracnose","Purple Blotch","Stemphylium Blight"], crops:["tomato","potato","pepper","banana","mango","onion"],
    dosage:"20 g/L water", frequency:"Every 14 days",
    description:"Traditional copper-lime mixture. Excellent preventive spray. Cost-effective, organic-approved, broad-spectrum.",
    featured:false, inStock:true, effectiveness:78,
    tags:["organic","diy","budget","preventive"],
    activeIngredient:"Copper sulfate + Calcium hydroxide", formulation:"Powder",
    phi:"7 days", safetyLevel:"Low"
  },
  {
    id:"m13", name:"Carbendazim 50% WP", brand:"Bavistin", company:"BASF India",
    category:"Fungicide", type:"chemical", price:290, mrp:340, unit:"250g",
    rating:4.5, reviews:1876, badge:"SOIL FUNGICIDE", badgeColor:"#2d7a31", emoji:"🟢",
    diseases:["Fusarium Wilt","Red Rot","Sheath Blight","Loose Smut"],
    crops:["cotton","sugarcane","rice","wheat","banana"],
    dosage:"1 g/L water (foliar) / 2 g/L (soil drench)", frequency:"Every 10–14 days",
    description:"Systemic benzimidazole fungicide. Excellent against soil-borne and vascular wilt diseases. Also used as seed treatment.",
    featured:true, inStock:true, effectiveness:91,
    tags:["systemic","wilt","soil-borne","seed-treatment"],
    activeIngredient:"Carbendazim 50%", formulation:"WP",
    phi:"3 days", safetyLevel:"Moderate"
  },
  {
    id:"m14", name:"Imidacloprid 17.8% SL", brand:"Confidor", company:"Bayer CropScience",
    category:"Insecticide (Vector Control)", type:"chemical", price:360, mrp:420, unit:"100 ml",
    rating:4.6, reviews:1123, badge:"VIRUS VECTOR CONTROL", badgeColor:"#0284c7", emoji:"🔷",
    diseases:["Curl Virus","Banana Mosaic","Sooty Mould","Grassy Shoot"],
    crops:["cotton","banana","mango","sugarcane"],
    dosage:"0.3 ml/L water", frequency:"Every 10–15 days",
    description:"Systemic neonicotinoid insecticide. Controls whitefly, aphids, and leafhoppers that transmit viral diseases. Seed and soil drench use possible.",
    featured:false, inStock:true, effectiveness:89,
    tags:["insecticide","vector-control","virus","whitefly"],
    activeIngredient:"Imidacloprid 17.8%", formulation:"SL (Soluble Liquid)",
    phi:"21 days", safetyLevel:"High"
  },
  {
    id:"m15", name:"Tricyclazole 75% WP", brand:"Beam 75 WP", company:"Dow AgroSciences",
    category:"Fungicide", type:"chemical", price:440, mrp:500, unit:"100g",
    rating:4.7, reviews:654, badge:"BLAST SPECIALIST", badgeColor:"#2d7a31", emoji:"🌱",
    diseases:["Blast","Anthracnose","Red Rot","Smut"],
    crops:["rice","mango","sugarcane","wheat"],
    dosage:"0.6 g/L water", frequency:"Every 14 days",
    description:"Highly effective melanin biosynthesis inhibitor. Best-in-class for rice blast. Also controls anthracnose and smut diseases in multiple crops.",
    featured:true, inStock:true, effectiveness:95,
    tags:["blast","melanin-inhibitor","rice-specialist","premium"],
    activeIngredient:"Tricyclazole 75%", formulation:"WP",
    phi:"5 days", safetyLevel:"Moderate"
  }
];

const DISEASE_MEDICINES = {
  // Existing
  "Leaf Blight":    ["m01","m02","m04","m08","m12"],
  "Early Blight":   ["m01","m03","m06","m08"],
  "Late Blight":    ["m03","m10","m01"],
  "Mildew":         ["m07","m05","m08"],
  "Rust":           ["m02","m05","m07"],
  "Spot":           ["m04","m01","m06","m08","m12"],
  "Bacterial Spot": ["m09","m11","m04","m12"],
  "Healthy":        ["m08","m07","m12"],
  // Banana
  "Cordana Leaf Spot": ["m01","m06","m08"],
  "Panama Wilt":       ["m13","m08"],
  "Sigatoka":          ["m02","m01","m07"],
  "Banana Mosaic":     ["m08","m14"],
  // Cotton
  "Bacterial Blight":  ["m09","m04","m12"],
  "Curl Virus":        ["m14","m08"],
  "Fusarium Wilt":     ["m13","m08"],
  "Leaf Spot":         ["m01","m06","m08"],
  // Mango
  "Anthracnose":       ["m15","m06","m04"],
  "Powdery Mildew":    ["m07","m05","m08"],
  "Sooty Mould":       ["m08","m14"],
  "Bacterial Canker":  ["m09","m04","m11"],
  // Onion
  "Purple Blotch":      ["m01","m06","m08"],
  "Stemphylium Blight": ["m04","m01","m12"],
  "Downy Mildew":       ["m03","m06","m08"],
  // Rice
  "Blast":                  ["m15","m06","m01"],
  "Brown Spot":             ["m01","m02","m08"],
  "Sheath Blight":          ["m13","m06","m04"],
  "Bacterial Leaf Blight":  ["m09","m04","m11"],
  // Sugarcane
  "Red Rot":      ["m13","m15","m04"],
  "Smut":         ["m15","m02","m07"],
  "Grassy Shoot": ["m14","m08"],
  "Leaf Scald":   ["m09","m04","m11"],
  // Wheat
  "Brown Rust":     ["m02","m05","m07"],
  "Yellow Rust":    ["m02","m05","m06"],
  "Loose Smut":     ["m15","m13","m01"],

};

const PROMOTED_IDS  = ["m06","m03","m09","m08"];
const FLASH_SALE_IDS = ["m01","m04","m07","m12"];

// ─── DISEASE INFO ─────────────────────────────────────────────────────────────
const DISEASE_INFO = {
  // ── Existing diseases ──────────────────────────────────────────────────
  "Healthy":        { severity:"none",     description:"Your crop appears healthy! No signs of disease detected.", causes:"Good agricultural practices are maintaining plant health.", remedies:{ prevention:["Continue regular irrigation","Maintain proper plant spacing","Apply balanced NPK fertilizer every 3–4 weeks","Monitor regularly for early signs of disease"] } },
  "Leaf Blight":    { severity:"moderate", description:"Leaf blight causes dark brown lesions that rapidly spread, leading to premature leaf drop and reduced yield.", causes:"Alternaria solani fungus. Thrives in warm (24–29°C), humid conditions.", remedies:{ organic:["Neem oil (3 ml/L) every 7 days","Copper-based Bordeaux mixture (1%)","Remove and destroy infected leaves","Mulch around base"], chemical:["Mancozeb 75% WP at 2.5 g/L every 7–10 days","Propiconazole 25% EC at 1 ml/L","Chlorothalonil 75% WP at 2 g/L"], prevention:["Use certified disease-resistant seeds","Maintain 60 cm plant spacing","Use drip irrigation","Rotate crops annually"] } },
  "Mildew":         { severity:"mild",     description:"Powdery mildew appears as white powdery patches on leaves. Reduces photosynthesis and weakens the plant.", causes:"Erysiphe spp. fungi. Spreads in dry weather with high humidity nights.", remedies:{ organic:["Baking soda solution (1 tsp/L + dish soap)","Diluted milk spray (1:9 ratio) weekly","Neem oil + garlic extract spray"], chemical:["Sulfur fungicide (3 g/L) every 14 days","Tebuconazole 25.9% EC at 1 ml/L"], prevention:["Improve ventilation","Water in the morning","Avoid excess nitrogen fertilization"] } },
  "Rust":           { severity:"severe",   description:"Rust causes orange-brown pustules on leaf undersides, severely reducing yield and plant vigor.", causes:"Puccinia species. Wind-borne spores. Favors cool, moist weather.", remedies:{ organic:["Sulfur dust on affected areas","Neem oil spray every 5–7 days"], chemical:["Propiconazole 25% EC at 1 ml/L","Tebuconazole 25.9% EC at 1 ml/L"], prevention:["Plant rust-resistant varieties","Avoid overhead irrigation"] } },
  "Spot":           { severity:"mild",     description:"Leaf spot manifests as circular brown spots with yellow halos, causing premature defoliation.", causes:"Multiple fungal/bacterial pathogens. Spreads through water splash.", remedies:{ organic:["Copper hydroxide spray (3 g/L)","Neem oil every 10 days"], chemical:["Copper oxychloride 50% WP at 3 g/L","Azoxystrobin 23% SC at 1 ml/L"], prevention:["Avoid working in wet fields","Mulch to reduce splash-back"] } },
  "Early Blight":   { severity:"moderate", description:"Early blight causes dark concentric-ring lesions on older leaves first, moving upward.", causes:"Alternaria solani fungus. Warm (24–29°C) humid conditions.", remedies:{ organic:["Neem oil (3 ml/L) every 7 days","Bordeaux mixture weekly"], chemical:["Mancozeb 75% WP 2.5 g/L","Azoxystrobin 23% SC 1 ml/L"], prevention:["Avoid overhead irrigation","Crop rotation every season"] } },
  "Late Blight":    { severity:"severe",   description:"Late blight is devastating — water-soaked lesions spread rapidly across the entire plant within days.", causes:"Phytophthora infestans. Spreads explosively in cool (10–20°C), wet weather.", remedies:{ organic:["Remove and destroy all infected tissue immediately","Copper sulfate spray"], chemical:["Metalaxyl + Mancozeb WP at 2.5 g/L","Cymoxanil + Mancozeb at 2 g/L"], prevention:["Plant only certified disease-free tubers","Scout fields twice weekly"] } },
  "Bacterial Spot": { severity:"moderate", description:"Bacterial spot causes water-soaked lesions that turn dark and scabby, affecting leaves and fruit.", causes:"Xanthomonas vesicatoria bacteria. Warm, wet, windy conditions.", remedies:{ organic:["Copper-based bactericide spray weekly","Remove heavily infected plants"], chemical:["Copper hydroxide 77% WP at 3 g/L","Streptomycin sulfate at 200 ppm"], prevention:["Use pathogen-free certified seed","Two-year crop rotation"] } },

  // ── Banana ────────────────────────────────────────────────────────────────
  "Cordana Leaf Spot": { severity:"mild",     description:"Oval brown spots with yellow halo on older leaves. Reduces photosynthetic area progressively.", causes:"Cordana musae fungus. Spreads in humid environments, especially during rainy season.", remedies:{ organic:["Remove badly infected leaves immediately","Neem oil (3 ml/L) every 10 days"], chemical:["Carbendazim 50% WP at 1 g/L","Mancozeb 75% WP at 2 g/L"], prevention:["Improve drainage around plants","Space plants to improve air circulation","Remove crop debris after harvest"] } },
  "Panama Wilt":       { severity:"severe",   description:"Banana Panama wilt (Fusarium wilt) causes yellowing, wilting, and complete collapse of the plant. No cure once infected.", causes:"Fusarium oxysporum f.sp. cubense fungus. Spreads through infected soil and planting material.", remedies:{ organic:["Remove and destroy infected plants with roots","Apply Trichoderma bio-fungicide to soil","Do not replant banana in infected soil for 5+ years"], chemical:["Soil drenching with Carbendazim 1g/L","Propiconazole 1 ml/L as preventive"], prevention:["Use certified disease-free tissue culture plants","Disinfect farming tools between plants","Grow resistant varieties (Cavendish)"] } },
  "Sigatoka":          { severity:"severe",   description:"Yellow Sigatoka and Black Sigatoka cause leaf streaks that expand into large necrotic patches, reducing yield up to 50%.", causes:"Mycosphaerella musicola / fijiensis fungus. Favors warm, humid, windy conditions.", remedies:{ organic:["Remove and destroy infected leaves weekly","Spray Bordeaux mixture every 14 days","Ensure adequate potassium nutrition"], chemical:["Propiconazole 25% EC at 1 ml/L","Mancozeb 75% WP at 2.5 g/L every 10 days"], prevention:["Use resistant varieties","Maintain proper spacing","Avoid waterlogging"] } },
  "Banana Mosaic":     { severity:"moderate", description:"Mosaic pattern on leaves — yellow and green mottling — stunts plant growth and severely reduces fruit yield.", causes:"Banana bract mosaic virus (BBrMV). Transmitted by aphids and infected planting material.", remedies:{ organic:["Remove and destroy infected plants immediately","Control aphid vectors with neem oil spray"], chemical:["No curative chemical — use systemic insecticides (Imidacloprid 0.5 ml/L) to control aphid vectors"], prevention:["Use certified virus-free tissue culture plants","Rogue out infected plants immediately","Control aphid population with yellow sticky traps"] } },

  // ── Cotton ────────────────────────────────────────────────────────────────
  "Bacterial Blight":  { severity:"severe",   description:"Angular water-soaked spots on leaves turning brown; severe infection causes premature defoliation and boll rot.", causes:"Xanthomonas axonopodis pv. malvacearum. Spreads through infected seeds and rain splash.", remedies:{ organic:["Remove infected plant debris","Apply Bordeaux mixture (1%) preventively","Avoid overhead irrigation"], chemical:["Streptomycin 90 SP at 200 ppm","Copper oxychloride 3 g/L every 10 days"], prevention:["Use certified disease-free seeds","Treat seeds with Streptocycline before sowing","Crop rotation with non-host crops"] } },
  "Curl Virus":        { severity:"severe",   description:"Leaves curl upward, become thick and leathery, turn yellow-green. Stunts plant severely. Can cause 100% yield loss if early infection.", causes:"Cotton leaf curl virus (CLCuV). Transmitted by whitefly (Bemisia tabaci). No cure once infected.", remedies:{ organic:["Remove and destroy infected plants early","Use yellow sticky traps for whitefly","Spray neem oil to control whitefly"], chemical:["Imidacloprid 17.8 SL at 0.3 ml/L for whitefly control","Thiamethoxam 25 WG at 0.3 g/L"], prevention:["Plant CLCuV-resistant varieties","Early sowing to avoid peak whitefly season","Remove alternate host weeds from field borders"] } },
  "Fusarium Wilt":     { severity:"severe",   description:"Yellowing and wilting of lower leaves progressing upward. Internal stem shows brown discolouration. Plant collapses.", causes:"Fusarium oxysporum f.sp. vasinfectum fungus. Soil-borne. Favors warm, humid soils.", remedies:{ organic:["Apply Trichoderma viride 4 g/kg seed as biocontrol","Soil solarisation in summer before sowing"], chemical:["Carbendazim 50% WP soil drench (1 g/L)","Seed treatment with Captan 75% WS (3 g/kg)"], prevention:["Use wilt-resistant certified varieties","Avoid waterlogging","Long crop rotation (4+ years) with cereals"] } },
  "Leaf Spot":         { severity:"mild",     description:"Circular to irregular brown spots on leaves with dark margins. Causes premature defoliation reducing photosynthesis.", causes:"Alternaria macrospora / Cercospora gossypina. Spreads in humid, warm conditions.", remedies:{ organic:["Remove infected leaves","Neem oil spray (3 ml/L) every 7 days"], chemical:["Mancozeb 75% WP at 2.5 g/L","Carbendazim 50% WP at 1 g/L"], prevention:["Avoid overhead irrigation","Balanced potassium fertilisation","Crop rotation"] } },

  // ── Mango ─────────────────────────────────────────────────────────────────
  "Anthracnose":      { severity:"moderate", description:"Dark sunken spots on leaves, flowers, and fruits. Causes premature fruit drop and post-harvest fruit rot.", causes:"Colletotrichum gloeosporioides fungus. Thrives in warm, wet, humid conditions especially at flowering.", remedies:{ organic:["Bordeaux mixture (1%) spray at bud break and fruit set","Remove infected plant parts","Improve canopy ventilation"], chemical:["Carbendazim 50% WP at 1 g/L pre- and post-bloom","Mancozeb 75% WP at 2.5 g/L"], prevention:["Prune trees for better air circulation","Avoid overhead irrigation","Apply protective sprays before monsoon"] } },
  "Powdery Mildew":   { severity:"mild",     description:"White powdery coating on young leaves, panicles, and fruits. Causes early flower and fruit drop.", causes:"Oidium mangiferae fungus. Spreads rapidly in dry weather with cool nights and warm days.", remedies:{ organic:["Sulfur dust (3 g/L) spray on affected parts","Wettable sulfur 80% WDG at 3 g/L"], chemical:["Dinocap 48% EC at 1 ml/L","Hexaconazole 5% EC at 1 ml/L"], prevention:["Prune dense canopy for air circulation","Spray preventively at panicle emergence","Avoid excessive nitrogen fertilizer"] } },
  "Sooty Mould":      { severity:"mild",     description:"Black sooty coating on leaf surfaces blocking sunlight. Weakens plant but does not directly infect tissue.", causes:"Capnodium mangiferae fungus growing on honeydew secreted by mealybugs and scale insects.", remedies:{ organic:["Control mealybugs with neem oil spray","Wash leaves with soap water to remove sooty mould","Release ladybird beetles as biological control"], chemical:["Spray Imidacloprid 0.3 ml/L to control sucking pests","Starch spray (2%) to physically remove mould"], prevention:["Regular inspection and pest monitoring","Control mealybugs and scale insects","Prune to improve air circulation"] } },
  "Bacterial Canker":  { severity:"severe",   description:"Water-soaked lesions on leaves, stems, and fruits turning yellow and cracking. Causes severe yield loss.", causes:"Xanthomonas campestris pv. mangiferaeindicae. Spreads through rain splash, tools, and infected nursery material.", remedies:{ organic:["Remove infected branches 15 cm below visible infection","Apply Bordeaux paste on cut surfaces","Avoid working in orchards when wet"], chemical:["Copper hydroxide 77% WP at 3 g/L","Streptomycin sulfate 90 SP at 200 ppm"], prevention:["Use certified disease-free nursery plants","Disinfect pruning tools with 1% bleach","Apply copper spray after pruning"] } },

  // ── Onion ─────────────────────────────────────────────────────────────────
  "Purple Blotch":       { severity:"moderate", description:"Water-soaked lesions turning white with purple centre on leaves. Severe infection collapses the entire foliage.", causes:"Alternaria porri fungus. Favors warm, humid weather with frequent dews.", remedies:{ organic:["Neem oil (3 ml/L) spray every 10 days","Remove infected crop debris immediately"], chemical:["Mancozeb 75% WP at 2.5 g/L","Iprodione 50% WP at 2 g/L","Hexaconazole 5 EC at 1 ml/L"], prevention:["Use certified healthy sets / transplants","Avoid excessive irrigation","Crop rotation with non-allium crops for 2+ years"] } },
  "Stemphylium Blight":  { severity:"mild",     description:"Small oval yellowish spots on leaf tips that enlarge and cause dieback of foliage. Coexists often with Purple Blotch.", causes:"Stemphylium vesicarium fungus. Favors warm humid conditions with high relative humidity.", remedies:{ organic:["Bordeaux mixture spray (0.5%)","Remove infected leaves"], chemical:["Chlorothalonil 75% WP at 2 g/L","Mancozeb 2.5 g/L + Iprodione 2 g/L tank mix"], prevention:["Avoid dense planting","Balanced nitrogen fertilisation","Avoid overhead irrigation"] } },
  "Downy Mildew":        { severity:"severe",   description:"Pale greenish-yellow patches on upper leaf surface with violet-grey fuzzy growth on the underside. Causes collapse of foliage.", causes:"Peronospora destructor oomycete. Spreads in cool, moist, foggy conditions.", remedies:{ organic:["Remove infected plants immediately","Spray Bordeaux mixture (1%) every 7 days"], chemical:["Metalaxyl + Mancozeb at 2.5 g/L","Cymoxanil 8% + Mancozeb 64% at 2 g/L"], prevention:["Plant in well-drained fields","Avoid late evening irrigation","Use resistant cultivars"] } },

  // ── Rice ──────────────────────────────────────────────────────────────────
  "Blast":                  { severity:"severe",   description:"Diamond-shaped grey-white lesions with brown margins on leaves. Node blast causes culm collapse. Can destroy entire crop.", causes:"Magnaporthe oryzae fungus. Spreads by wind-borne spores. Favors humid, cool nights and nitrogen-rich fields.", remedies:{ organic:["Spray Pseudomonas fluorescens biocontrol (5 g/L)","Silicon application strengthens cell walls"], chemical:["Tricyclazole 75% WP at 0.6 g/L","Isoprothiolane 40% EC at 1.5 ml/L"], prevention:["Use blast-resistant varieties","Avoid excess nitrogen","Split nitrogen application","Drain fields intermittently"] } },
  "Brown Spot":             { severity:"moderate", description:"Oval to circular brown spots on leaves with yellow halo. Causes significant grain discolouration and yield loss.", causes:"Helminthosporium oryzae fungus. Associated with nutrient-deficient soils, especially low potassium.", remedies:{ organic:["Apply adequate potassium and zinc fertilizer","Seed treatment with Pseudomonas fluorescens (10 g/kg)"], chemical:["Mancozeb 75% WP at 2 g/L","Propiconazole 25% EC at 1 ml/L"], prevention:["Balanced NPK fertilisation","Use certified healthy seeds","Seed treatment before sowing"] } },
  "Sheath Blight":          { severity:"moderate", description:"Water-soaked irregular lesions on leaf sheath with grey-white centre and brown border. Causes lodging and grain sterility.", causes:"Rhizoctonia solani fungus. Favors dense planting, high humidity, and high nitrogen levels.", remedies:{ organic:["Apply Trichoderma viride 4 kg/acre as bio-fungicide","Spray Pseudomonas fluorescens"], chemical:["Validamycin 3% L at 2 ml/L","Hexaconazole 5% EC at 1 ml/L"], prevention:["Maintain recommended plant spacing","Avoid excess nitrogen application","Drain fields to reduce humidity"] } },
  "Bacterial Leaf Blight":  { severity:"severe",   description:"Water-soaked to yellowish stripe along leaf margins progressing to whitish-grey. Causes kresek (wilting) in young plants.", causes:"Xanthomonas oryzae pv. oryzae bacteria. Spreads through water, wind, and infected transplants.", remedies:{ organic:["Remove infected plants in nursery immediately","Avoid flood irrigation during outbreak"], chemical:["Copper oxychloride 50% WP at 3 g/L","Streptomycin 90 SP + Copper hydroxide tank mix"], prevention:["Use resistant varieties","Avoid transplanting during typhoon season","Balanced nitrogen nutrition"] } },

  // ── Sugarcane ─────────────────────────────────────────────────────────────
  "Red Rot":       { severity:"severe",   description:"Stalk shows red discolouration with white patches inside. Leaves dry up, plant dies rapidly. Major cause of cane quality loss.", causes:"Colletotrichum falcatum fungus. Spreads through infected seed cane, waterlogged soil, high humidity.", remedies:{ organic:["Rogue out infected clumps and destroy","Hot water seed treatment (52°C for 30 min)"], chemical:["Carbendazim seed sett treatment (1 g/L for 5 min)","Tridemorph 81% EC as preventive foliar"], prevention:["Use disease-free certified seed cane","Select resistant varieties","Avoid waterlogging — improve drainage"] } },
  "Smut":          { severity:"moderate", description:"Black whip-like sorus emerging from growing point. Infected plants are stunted and produce no cane.", causes:"Sporisorium scitamineum fungus. Wind-borne spores infect developing buds during germination.", remedies:{ organic:["Rogue infected plants immediately","Hot water treatment of seed setts (52°C, 30 min)"], chemical:["Carbendazim 50% WP sett treatment","Propiconazole foliar spray as preventive"], prevention:["Plant smut-resistant varieties","Use disease-free planting material","Rogue smutted plants before tasseling"] } },
  "Grassy Shoot":  { severity:"severe",   description:"Excessive tiller production of thin, pale-yellow shoots resembling grass. No harvestable cane produced. Entire plant is sterile.", causes:"Sugarcane grassy shoot phytoplasma (MLO). Transmitted by leafhopper (Pyrilla perpusilla) insect vector.", remedies:{ organic:["Rogue out infected plants immediately — no cure","Control leafhopper with neem oil spray (3 ml/L)"], chemical:["Imidacloprid 0.3 ml/L for leafhopper vector control","No chemical cure for the phytoplasma itself"], prevention:["Use disease-free tissue culture plants","Control leafhopper population","Hot water treatment of seed setts"] } },
  "Leaf Scald":    { severity:"moderate", description:"White pencil-line streaks on leaves extending from tip. Advanced infection causes leaf tip scorch and stalk rot.", causes:"Xanthomonas albilineans bacteria. Spreads through infected seed cane and tools.", remedies:{ organic:["Hot water treatment of seed setts (50°C for 2 hours)","Rogue infected plants"], chemical:["Streptomycin 90 SP at 200 ppm sett soak","Copper oxychloride 3 g/L foliar spray"], prevention:["Use certified disease-free seed cane","Disinfect harvesting tools with bleach","Avoid ratoon from infected crop"] } },

  // ── Wheat ─────────────────────────────────────────────────────────────────
  "Brown Rust":   { severity:"severe",   description:"Orange-brown oval pustules on leaf surfaces, mainly on upper side. Rapid spread reduces grain filling causing shrivelled grains.", causes:"Puccinia triticina fungus. Wind-borne spores. Spreads explosively in warm (15–22°C), humid conditions.", remedies:{ organic:["Sulfur dust (3 g/L) at first sign","Remove volunteer wheat plants from surrounding areas"], chemical:["Propiconazole 25% EC at 1 ml/L","Tebuconazole 25.9% EC at 1 ml/L","Hexaconazole 5% EC at 2 ml/L"], prevention:["Plant brown rust–resistant varieties","Early sowing to avoid peak rust season","Use balanced potassium fertiliser"] } },
  "Yellow Rust":  { severity:"severe",   description:"Yellow-orange pustules arranged in stripes along the leaf. Very rapid spread in cool conditions. Can cause near-complete yield loss.", causes:"Puccinia striiformis fungus. Wind-borne. Favors cool (10–15°C), moist conditions. New virulent races spread very fast.", remedies:{ organic:["Remove and destroy heavily infected crop early","Sulfur-based fungicide as protective measure"], chemical:["Propiconazole 25% EC at 1 ml/L — spray immediately at first sign","Tebuconazole + Trifloxystrobin combination"], prevention:["Plant yellow rust–resistant varieties","Monitor fields weekly during February–March","Early timely sowing"] } },
  "Loose Smut":   { severity:"moderate", description:"Grain is replaced by a mass of brown-black powdery spores. Entire head turns into a sooty mass that disperses early in the season.", causes:"Ustilago tritici fungus. Seed-borne. Infects the embryo at flowering stage. Spreads through wind.", remedies:{ organic:["Hot water seed treatment (49°C for 20 min)","Biocontrol — Trichoderma seed treatment (4 g/kg)"], chemical:["Carboxin 37.5% + Thiram 37.5% DS seed treatment (3 g/kg)","Carbendazim 50% WP seed treatment (2.5 g/kg)"], prevention:["Use certified smut-free seeds","Seed treatment is the most effective control","Rogue infected plants before spore dispersal"] } },
 
};

const SEVERITY_CONFIG = {
  none:     { color:"#16a34a", bg:"rgba(22,163,74,0.12)",   label:"Healthy",  icon:"✓" },
  mild:     { color:"#ca8a04", bg:"rgba(202,138,4,0.12)",   label:"Mild",     icon:"!" },
  moderate: { color:"#ea580c", bg:"rgba(234,88,12,0.12)",   label:"Moderate", icon:"!!" },
  severe:   { color:"#dc2626", bg:"rgba(220,38,38,0.12)",   label:"Severe",   icon:"!!!" }
};
const TYPE_CONFIG = {
  chemical:           { label:"Chemical",         color:"#0284c7", bg:"rgba(2,132,199,0.1)"  },
  organic:            { label:"Organic",           color:"#16a34a", bg:"rgba(22,163,74,0.1)"  },
  "organic-approved": { label:"Organic Approved", color:"#16a34a", bg:"rgba(22,163,74,0.1)"  }
};
const CROP_EMOJIS = {
  tomato:"🍅", potato:"🥔", pepper:"🌶️",
  banana:"🍌", cotton:"🌸", mango:"🥭",
  onion:"🧅",  rice:"🌾",   sugarcane:"🎋", wheat:"🌾"
};

// Category groups for the crop grid
const CROP_GROUPS = [
  {
    label: "Vegetables",
    crops: [
      { key:"tomato",   name:"Tomato",    diseases:"Blight · Mildew · Rust · Spot" },
      { key:"potato",   name:"Potato",    diseases:"Early Blight · Late Blight" },
      { key:"pepper",   name:"Pepper",    diseases:"Bacterial Spot" },
      { key:"onion",    name:"Onion",     diseases:"Purple Blotch · Downy Mildew" },
    ]
  },
  {
    label: "Fruits",
    crops: [
      { key:"mango",    name:"Mango",     diseases:"Anthracnose · Powdery Mildew" },
      { key:"banana",   name:"Banana",    diseases:"Sigatoka · Panama Wilt" },
    ]
  },
  {
    label: "Field Crops",
    crops: [
      { key:"rice",       name:"Rice",       diseases:"Blast · Brown Spot · Sheath Blight" },
      { key:"wheat",      name:"Wheat",      diseases:"Brown Rust · Yellow Rust · Smut" },
      { key:"sugarcane",  name:"Sugarcane",  diseases:"Red Rot · Smut · Grassy Shoot" },
      { key:"cotton",     name:"Cotton",     diseases:"Blight · Curl Virus · Fusarium Wilt" },
    ]
  }
];
// ── API URL ───────────────────────────────────────────────────────────────────
// On Vercel: set VITE_API_URL = https://your-app.onrender.com  (no trailing slash)
// On localhost: vite proxy forwards /api → localhost:8000, so use ""
const API_URL = (() => {
  const env = import.meta.env.VITE_API_URL;
  if (env && env.trim() !== "") return env.trim().replace(/\/$/, "");
  // In dev (localhost) the vite proxy handles /api → no base URL needed
  return "";
})();

async function runDetection(file, crop) {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("crop", crop);

  const controller = new AbortController();
  // 90s timeout — Render free tier can take 30s cold start
  const tid = setTimeout(() => controller.abort(), 90_000);

  let res;
  try {
    res = await fetch(`${API_URL}/api/detect`, {
      method: "POST",
      body:   fd,
      signal: controller.signal,
    });
  } catch (err) {
    clearTimeout(tid);
    if (err.name === "AbortError") {
      throw new Error(
        "Request timed out (90s). The server may be waking up — please wait 30 seconds and try again."
      );
    }
    // Network-level failure — usually CORS block or server down
    throw new Error(
      `Cannot reach the CropAI server.\n\n` +
      `• Check: is VITE_API_URL set correctly on Vercel?\n` +
      `• Current API target: ${API_URL || "(empty — using vite proxy)"}\n` +
      `• Original error: ${err.message}`
    );
  }
  clearTimeout(tid);

  if (!res.ok) {
    let detail = `Server error ${res.status}`;
    try { const j = await res.json(); detail = j.detail || j.message || detail; } catch {}
    throw new Error(detail);
  }

  return res.json();
}

// ─── CART HOOK ────────────────────────────────────────────────────────────────
function useCart() {
  const [items, setItems] = useState([]);
  const add    = (med, qty=1) => setItems(p => { const ex=p.find(i=>i.id===med.id); return ex?p.map(i=>i.id===med.id?{...i,qty:i.qty+qty}:i):[...p,{...med,qty}]; });
  const remove = (id)   => setItems(p => p.filter(i=>i.id!==id));
  const clear  = ()     => setItems([]);
  const total  = items.reduce((s,i)=>s+i.price*i.qty,0);
  const count  = items.reduce((s,i)=>s+i.qty,0);
  return { items, add, remove, clear, total, count };
}

// ─── SHARED COMPONENTS ────────────────────────────────────────────────────────
function ConfBar({ label, value, color="#4caf50", delay=0 }) {
  return (
    <div style={{ marginBottom:10 }}>
      <div style={{ display:"flex", justifyContent:"space-between", fontSize:13, marginBottom:5, color:"var(--text2)" }}>
        <span>{label}</span>
        <span style={{ fontFamily:"var(--mono)", color, fontWeight:600 }}>{value.toFixed(1)}%</span>
      </div>
      <div style={{ height:6, background:"var(--border-bg)", borderRadius:3, overflow:"hidden" }}>
        <div style={{ height:"100%", borderRadius:3, background:`linear-gradient(90deg,${color}99,${color})`, width:`${value}%`, animation:`barIn 0.8s ${delay}s cubic-bezier(.4,0,.2,1) both` }} />
      </div>
    </div>
  );
}

function SeverityBadge({ disease }) {
  const sev = SEVERITY_CONFIG[(DISEASE_INFO[disease]||{}).severity||"moderate"];
  return <span style={{ display:"inline-flex", alignItems:"center", gap:6, padding:"4px 12px", borderRadius:20, background:sev.bg, color:sev.color, fontWeight:700, fontSize:12 }}>{sev.icon} {sev.label}</span>;
}

function Stars({ rating }) {
  return <span style={{ display:"inline-flex", gap:2 }}>{[1,2,3,4,5].map(i=><span key={i} style={{ fontSize:11, color:i<=Math.round(rating)?"#f59e0b":"var(--border2)" }}>★</span>)}</span>;
}

function DiscountBadge({ price, mrp }) {
  const pct = Math.round((1-price/mrp)*100);
  if (pct<=0) return null;
  return <span style={{ fontSize:11, fontWeight:800, color:"#dc2626", background:"rgba(220,38,38,0.1)", padding:"2px 7px", borderRadius:4 }}>{pct}% OFF</span>;
}

// ─── MEDICINE CARD ────────────────────────────────────────────────────────────
function MedicineCard({ med, onBuy, onAddCart, compact=false }) {
  const tc = TYPE_CONFIG[med.type]||TYPE_CONFIG.chemical;
  const [cartFlash, setCartFlash] = useState(false);
  const handleAdd = () => { onAddCart&&onAddCart(med); setCartFlash(true); setTimeout(()=>setCartFlash(false),1800); };
  return (
    <div className="card hover-lift" style={{ padding:compact?16:22, position:"relative", overflow:"hidden", opacity:med.inStock?1:0.62, display:"flex", flexDirection:compact?"row":"column", gap:compact?16:0, alignItems:compact?"center":undefined }}>
      {!med.inStock && <div style={{ position:"absolute", inset:0, background:"rgba(255,255,255,0.55)", zIndex:2, display:"flex", alignItems:"center", justifyContent:"center" }}><span style={{ fontWeight:800, color:"#dc2626", fontSize:13, background:"#fff", padding:"5px 12px", borderRadius:7, border:"1px solid rgba(220,38,38,0.25)" }}>OUT OF STOCK</span></div>}
      {med.badge&&!compact && <div style={{ position:"absolute", top:10, right:10, background:med.badgeColor, color:"#fff", fontSize:9, fontWeight:800, letterSpacing:0.8, padding:"3px 8px", borderRadius:4 }}>{med.badge}</div>}

      {/* Icon + header */}
      <div style={{ display:"flex", gap:12, alignItems:"flex-start", marginBottom:compact?0:12, flexShrink:compact?0:undefined }}>
        <div style={{ width:compact?40:50, height:compact?40:50, flexShrink:0, borderRadius:10, background:"var(--bg3)", display:"flex", alignItems:"center", justifyContent:"center", fontSize:compact?"1.4rem":"1.8rem", border:"1px solid var(--border)" }}>{med.emoji}</div>
        {!compact && (
          <div style={{ flex:1, minWidth:0 }}>
            <div style={{ fontWeight:700, fontSize:"0.93rem", lineHeight:1.3, marginBottom:3 }}>{med.name}</div>
            <div style={{ fontSize:11, color:"var(--text3)", marginBottom:5 }}>{med.brand} · {med.company}</div>
            <div style={{ display:"flex", gap:5, flexWrap:"wrap" }}>
              <span style={{ fontSize:10, fontWeight:700, padding:"2px 7px", borderRadius:4, background:tc.bg, color:tc.color }}>{tc.label}</span>
              <span style={{ fontSize:10, padding:"2px 7px", borderRadius:4, background:"var(--bg3)", color:"var(--text3)" }}>{med.category}</span>
            </div>
          </div>
        )}
      </div>

      {/* Compact: name + price inline */}
      {compact && (
        <div style={{ flex:1, minWidth:0 }}>
          <div style={{ display:"flex", alignItems:"center", gap:8, flexWrap:"wrap" }}>
            <span style={{ fontWeight:700, fontSize:"0.9rem" }}>{med.name}</span>
            {med.badge&&<span style={{ background:med.badgeColor, color:"#fff", fontSize:9, fontWeight:800, padding:"2px 7px", borderRadius:3 }}>{med.badge}</span>}
          </div>
          <div style={{ fontSize:11, color:"var(--text3)", marginBottom:4 }}>{med.brand} · {med.company}</div>
          <div style={{ display:"flex", gap:6, alignItems:"center", flexWrap:"wrap" }}>
            <span style={{ fontFamily:"var(--display)", fontWeight:800, fontSize:"1rem" }}>₹{med.price}</span>
            {med.mrp>med.price&&<span style={{ fontSize:11, color:"var(--text3)", textDecoration:"line-through" }}>₹{med.mrp}</span>}
            <DiscountBadge price={med.price} mrp={med.mrp} />
            <Stars rating={med.rating} />
            <span style={{ fontSize:11, color:"var(--text3)" }}>({med.reviews.toLocaleString()})</span>
          </div>
          <div style={{ display:"flex", gap:4, marginTop:6, flexWrap:"wrap" }}>
            {med.diseases.slice(0,3).map(d=><span key={d} style={{ fontSize:10, padding:"1px 7px", borderRadius:3, background:"rgba(76,175,80,0.08)", color:"var(--green)", border:"1px solid rgba(76,175,80,0.18)" }}>✓ {d}</span>)}
          </div>
        </div>
      )}

      {/* Full card body */}
      {!compact && <>
        <div style={{ marginBottom:10 }}>
          <div style={{ display:"flex", justifyContent:"space-between", fontSize:11, marginBottom:4, color:"var(--text3)" }}>
            <span>Effectiveness</span>
            <span style={{ fontFamily:"var(--mono)", fontWeight:700, color:med.effectiveness>=90?"var(--green)":"#ca8a04" }}>{med.effectiveness}%</span>
          </div>
          <div style={{ height:4, background:"var(--border-bg)", borderRadius:2 }}>
            <div style={{ height:"100%", borderRadius:2, width:`${med.effectiveness}%`, background:med.effectiveness>=90?"linear-gradient(90deg,#4caf50,#2d7a31)":"linear-gradient(90deg,#f59e0b,#ca8a04)" }} />
          </div>
        </div>
        <p style={{ fontSize:13, color:"var(--text2)", lineHeight:1.6, marginBottom:10, flexGrow:0 }}>{med.description}</p>
        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:8, marginBottom:10, padding:"10px 12px", background:"var(--bg2)", borderRadius:8, border:"1px solid var(--border)" }}>
          <div><div style={{ fontSize:10, color:"var(--text3)", letterSpacing:0.5, marginBottom:2 }}>DOSAGE</div><div style={{ fontSize:12, fontWeight:600, fontFamily:"var(--mono)" }}>{med.dosage}</div></div>
          <div><div style={{ fontSize:10, color:"var(--text3)", letterSpacing:0.5, marginBottom:2 }}>FREQUENCY</div><div style={{ fontSize:12, fontWeight:600 }}>{med.frequency}</div></div>
        </div>
        <div style={{ display:"flex", flexWrap:"wrap", gap:5, marginBottom:12 }}>
          {med.diseases.map(d=><span key={d} style={{ fontSize:11, padding:"2px 9px", borderRadius:4, background:"rgba(76,175,80,0.08)", color:"var(--green)", border:"1px solid rgba(76,175,80,0.2)", fontWeight:500 }}>✓ {d}</span>)}
        </div>
      </>}

      {/* Price + CTA */}
      <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginTop:compact?0:"auto", paddingTop:compact?0:4, flexShrink:compact?0:undefined, gap:8 }}>
        {!compact && (
          <div>
            <div style={{ display:"flex", alignItems:"baseline", gap:6 }}>
              <span style={{ fontFamily:"var(--display)", fontWeight:800, fontSize:"1.2rem" }}>₹{med.price}</span>
              {med.mrp>med.price&&<span style={{ fontSize:11, color:"var(--text3)", textDecoration:"line-through" }}>₹{med.mrp}</span>}
              <DiscountBadge price={med.price} mrp={med.mrp} />
            </div>
            <div style={{ display:"flex", alignItems:"center", gap:5, marginTop:2 }}>
              <Stars rating={med.rating} />
              <span style={{ fontSize:11, color:"var(--text3)" }}>{med.rating} ({med.reviews.toLocaleString()})</span>
            </div>
          </div>
        )}
        {med.inStock && (
          <div style={{ display:"flex", gap:6, marginLeft:compact?"auto":undefined }}>
            <button title={cartFlash?"Added!":"Add to cart"} onClick={handleAdd}
              style={{ padding:"8px 10px", borderRadius:8, background:cartFlash?"rgba(76,175,80,0.15)":"var(--bg2)", border:`1px solid ${cartFlash?"var(--green)":"var(--border)"}`, cursor:"pointer", fontSize:compact?13:16, color:cartFlash?"var(--green)":"var(--text2)", transition:"all .2s", fontWeight:cartFlash?700:400 }}>
              {cartFlash?"✓":"🛒"}
            </button>
            <button className="btn btn-primary" style={{ padding:compact?"7px 14px":"8px 16px", fontSize:13 }} onClick={()=>onBuy&&onBuy(med)}>
              Buy Now
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── BUY MODAL ────────────────────────────────────────────────────────────────
function BuyModal({ med, onClose, onAddCart }) {
  const [qty, setQty] = useState(1);
  const [added, setAdded] = useState(false);
  if (!med) return null;
  return (
    <div style={{ position:"fixed", inset:0, zIndex:1000, background:"rgba(0,0,0,0.55)", backdropFilter:"blur(6px)", display:"flex", alignItems:"center", justifyContent:"center", padding:20 }} onClick={onClose}>
      <div className="card" style={{ width:"100%", maxWidth:480, padding:28, animation:"fadeUp 0.25s both", maxHeight:"90vh", overflowY:"auto" }} onClick={e=>e.stopPropagation()}>
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:20 }}>
          <div style={{ display:"flex", gap:14, alignItems:"center" }}>
            <div style={{ fontSize:"2.5rem" }}>{med.emoji}</div>
            <div>
              <div style={{ fontFamily:"var(--display)", fontWeight:700, fontSize:"1.1rem", marginBottom:2 }}>{med.name}</div>
              <div style={{ fontSize:13, color:"var(--text3)" }}>{med.brand} · {med.unit}</div>
              {med.badge&&<div style={{ display:"inline-block", marginTop:4, background:med.badgeColor, color:"#fff", fontSize:9, fontWeight:800, letterSpacing:0.8, padding:"2px 8px", borderRadius:4 }}>{med.badge}</div>}
            </div>
          </div>
          <button onClick={onClose} style={{ background:"none", border:"none", cursor:"pointer", fontSize:"1.3rem", color:"var(--text3)", padding:4 }}>✕</button>
        </div>

        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:8, marginBottom:16 }}>
          {[["Active Ingredient",med.activeIngredient],["Formulation",med.formulation],["Dosage",med.dosage],["Frequency",med.frequency],["Pre-Harvest Interval",med.phi],["Safety Level",med.safetyLevel]].map(([k,v])=>(
            <div key={k} style={{ padding:"9px 12px", background:"var(--bg2)", borderRadius:8, border:"1px solid var(--border)" }}>
              <div style={{ fontSize:10, color:"var(--text3)", letterSpacing:0.5, marginBottom:2 }}>{k.toUpperCase()}</div>
              <div style={{ fontSize:12, fontWeight:600 }}>{v||"—"}</div>
            </div>
          ))}
        </div>

        <div style={{ padding:"12px 14px", background:"rgba(76,175,80,0.06)", borderRadius:8, marginBottom:16, border:"1px solid rgba(76,175,80,0.2)", fontSize:13, color:"var(--text2)", lineHeight:1.6 }}>
          <strong style={{color:"var(--green)"}}>Usage: </strong>Mix <strong>{med.dosage}</strong> in clean water. Spray all leaf surfaces. Repeat <strong>{med.frequency}</strong>. Apply early morning or evening. Wear gloves and mask.
        </div>

        <div style={{ display:"flex", alignItems:"center", gap:16, marginBottom:20 }}>
          <span style={{ fontSize:13, fontWeight:600, color:"var(--text2)" }}>Quantity:</span>
          <div style={{ display:"flex", alignItems:"center", gap:10, background:"var(--bg2)", borderRadius:8, padding:"6px 14px", border:"1px solid var(--border)" }}>
            <button onClick={()=>setQty(q=>Math.max(1,q-1))} style={{ background:"none", border:"none", cursor:"pointer", fontFamily:"var(--body)", fontSize:"1.1rem", color:"var(--text2)", padding:"0 2px" }}>−</button>
            <span style={{ fontFamily:"var(--mono)", fontWeight:700, minWidth:20, textAlign:"center" }}>{qty}</span>
            <button onClick={()=>setQty(q=>q+1)} style={{ background:"none", border:"none", cursor:"pointer", fontFamily:"var(--body)", fontSize:"1.1rem", color:"var(--green)", padding:"0 2px" }}>+</button>
          </div>
          <div style={{ marginLeft:"auto" }}>
            <div style={{ fontFamily:"var(--display)", fontWeight:800, fontSize:"1.4rem", color:"var(--green)" }}>₹{med.price*qty}</div>
            {med.mrp>med.price&&<div style={{ fontSize:11, color:"var(--text3)", textDecoration:"line-through", textAlign:"right" }}>₹{med.mrp*qty}</div>}
          </div>
        </div>

        <div style={{ display:"flex", gap:10, marginBottom:12 }}>
          <button className="btn btn-ghost" style={{ flex:1 }} onClick={()=>{ onAddCart&&onAddCart(med,qty); setAdded(true); setTimeout(()=>setAdded(false),2500); }}>
            {added?"✓ Added to Cart!":"🛒 Add to Cart"}
          </button>
          <button className="btn btn-primary" style={{ flex:1 }} onClick={()=>{ alert(`✅ Order placed!\n\n${qty}× ${med.name} (${med.unit})\nTotal: ₹${med.price*qty}\n\nIntegrate Razorpay/PayU for real payments.`); onClose(); }}>
            Buy Now · ₹{med.price*qty}
          </button>
        </div>
        <div style={{ fontSize:11, color:"var(--text3)", textAlign:"center", lineHeight:1.8 }}>
          🚚 Free delivery above ₹500 &nbsp;·&nbsp; 🔒 Secure checkout &nbsp;·&nbsp; ↩ 7-day returns
        </div>
      </div>
    </div>
  );
}

// ─── CART DRAWER ──────────────────────────────────────────────────────────────
function CartDrawer({ cart, onClose }) {
  return (
    <div style={{ position:"fixed", inset:0, zIndex:900, display:"flex", justifyContent:"flex-end" }} onClick={onClose}>
      <div style={{ width:"100%", maxWidth:400, background:"var(--bg)", borderLeft:"1px solid var(--border)", display:"flex", flexDirection:"column", animation:"slideIn 0.25s both", boxShadow:"-8px 0 40px rgba(0,0,0,0.1)" }} onClick={e=>e.stopPropagation()}>
        <div style={{ padding:"20px 24px", borderBottom:"1px solid var(--border)", display:"flex", justifyContent:"space-between", alignItems:"center" }}>
          <div>
            <h3 style={{ fontFamily:"var(--display)", fontWeight:700, fontSize:"1.1rem" }}>Your Cart</h3>
            <div style={{ fontSize:12, color:"var(--text3)" }}>{cart.count} item{cart.count!==1?"s":""}</div>
          </div>
          <button onClick={onClose} style={{ background:"none", border:"none", cursor:"pointer", fontSize:"1.3rem", color:"var(--text3)" }}>✕</button>
        </div>
        <div style={{ flex:1, overflowY:"auto", padding:"16px 24px" }}>
          {cart.items.length===0
            ? <div style={{ textAlign:"center", paddingTop:60, color:"var(--text3)" }}><div style={{fontSize:"3rem",marginBottom:12}}>🛒</div><div style={{fontWeight:600,marginBottom:6}}>Cart is empty</div><div style={{fontSize:13}}>Add medicines to get started.</div></div>
            : cart.items.map(item=>(
              <div key={item.id} style={{ display:"flex", gap:12, padding:"14px 0", borderBottom:"1px solid var(--border)", alignItems:"center" }}>
                <div style={{ fontSize:"1.8rem" }}>{item.emoji}</div>
                <div style={{ flex:1 }}>
                  <div style={{ fontWeight:600, fontSize:"0.88rem" }}>{item.name}</div>
                  <div style={{ fontSize:12, color:"var(--text3)" }}>{item.unit} · ×{item.qty}</div>
                </div>
                <div style={{ textAlign:"right" }}>
                  <div style={{ fontWeight:700, fontFamily:"var(--display)" }}>₹{item.price*item.qty}</div>
                  <button onClick={()=>cart.remove(item.id)} style={{ fontSize:11, color:"#dc2626", background:"none", border:"none", cursor:"pointer", fontFamily:"var(--body)", marginTop:2 }}>Remove</button>
                </div>
              </div>
            ))
          }
        </div>
        {cart.items.length>0&&(
          <div style={{ padding:"20px 24px", borderTop:"1px solid var(--border)" }}>
            <div style={{ display:"flex", justifyContent:"space-between", marginBottom:4, fontSize:14, color:"var(--text2)" }}><span>Subtotal</span><span style={{fontFamily:"var(--mono)"}}>₹{cart.total}</span></div>
            <div style={{ display:"flex", justifyContent:"space-between", marginBottom:4, fontSize:13, color:"var(--text3)" }}><span>Delivery</span><span>{cart.total>=500?"FREE":"₹49"}</span></div>
            <div style={{ display:"flex", justifyContent:"space-between", fontSize:16, fontWeight:700, borderTop:"1px solid var(--border)", paddingTop:10, marginTop:8, marginBottom:20 }}>
              <span>Total</span>
              <span style={{ fontFamily:"var(--display)", color:"var(--green)" }}>₹{cart.total+(cart.total>=500?0:49)}</span>
            </div>
            <button className="btn btn-primary" style={{ width:"100%", padding:"13px", fontSize:"0.95rem" }} onClick={()=>{ alert(`✅ Order placed!\n\n${cart.count} items · ₹${cart.total+(cart.total>=500?0:49)}\n\nIntegrate Razorpay/PayU for real payments.`); cart.clear(); onClose(); }}>
              Checkout →
            </button>
            <div style={{ fontSize:11, color:"var(--text3)", textAlign:"center", marginTop:10 }}>
              Use code <strong style={{fontFamily:"var(--mono)",color:"var(--green)"}}>CROPAI10</strong> for 10% off first order
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── PAGE: HOME ────────────────────────────────────────────────────────────────
function HomePage({ onStart, onMedicines, cart }) {
  const promotedMeds  = PROMOTED_IDS.map(id=>MEDICINES.find(m=>m.id===id));
  const flashSaleMeds = FLASH_SALE_IDS.map(id=>MEDICINES.find(m=>m.id===id));

  return (
    <div>
      {/* HERO */}
      <div style={{ minHeight:"calc(100vh - 64px)", display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", textAlign:"center", padding:"80px 5% 60px", position:"relative", overflow:"hidden" }}>
        <div style={{ position:"absolute", inset:0, background:"radial-gradient(ellipse 70% 50% at 50% 40%, rgba(76,175,80,0.07) 0%, transparent 70%)", pointerEvents:"none" }} />
        <div className="fade-up" style={{ display:"inline-flex", alignItems:"center", gap:8, background:"rgba(76,175,80,0.1)", border:"1px solid rgba(76,175,80,0.25)", color:"var(--green)", padding:"6px 16px", borderRadius:20, fontSize:12, fontWeight:700, letterSpacing:2, textTransform:"uppercase", marginBottom:28 }}>
          <span style={{ width:6, height:6, borderRadius:"50%", background:"var(--green)", animation:"pulse 2s infinite" }} />
          AI-Powered Crop Disease Detection
        </div>
        <h1 className="fade-up" style={{ fontFamily:"var(--display)", fontSize:"clamp(2.8rem,6vw,4.5rem)", fontWeight:800, lineHeight:1.08, letterSpacing:"-2px", marginBottom:24, maxWidth:760, animationDelay:"0.1s" }}>
          Detect Disease.<br /><span style={{color:"var(--green)"}}>Buy the Cure.</span>
        </h1>
        <p className="fade-up" style={{ fontSize:"1.1rem", color:"var(--text2)", lineHeight:1.8, maxWidth:580, marginBottom:36, fontWeight:300, animationDelay:"0.2s" }}>
          Upload a leaf photo — YOLO + ResNet + Grad-CAM identifies the disease in seconds, then prescribes the exact medicine to buy.
        </p>
        <div className="fade-up" style={{ display:"flex", gap:12, flexWrap:"wrap", justifyContent:"center", animationDelay:"0.3s" }}>
          <button className="btn btn-primary btn-lg" onClick={onStart}>Analyse My Crop →</button>
          <button className="btn btn-ghost btn-lg" onClick={onMedicines}>💊 Browse Medicines</button>
        </div>
        <div className="fade-up" style={{ display:"flex", gap:40, marginTop:56, animationDelay:"0.4s" }}>
          {[["10","Crops"],["30+","Diseases"],["15","Medicines"],["94%","Accuracy*"]].map(([n,l])=>(
            <div key={l} style={{ textAlign:"center" }}>
              <div style={{ fontFamily:"var(--display)", fontSize:"2rem", fontWeight:800, color:"var(--green)" }}>{n}</div>
              <div style={{ fontSize:12, color:"var(--text3)", letterSpacing:1 }}>{l}</div>
            </div>
          ))}
        </div>
      </div>

      {/* FLASH SALE BANNER */}
      <div style={{ background:"linear-gradient(135deg,#1e5c21,#2d7a31)", padding:"26px 5%", display:"flex", alignItems:"center", justifyContent:"space-between", flexWrap:"wrap", gap:16 }}>
        <div style={{ display:"flex", alignItems:"center", gap:16 }}>
          <span style={{ fontSize:"2rem" }}>⚡</span>
          <div>
            <div style={{ fontFamily:"var(--display)", fontWeight:800, fontSize:"1.1rem", color:"#fff", marginBottom:2 }}>Flash Sale — Up to 21% off budget treatments</div>
            <div style={{ fontSize:13, color:"rgba(255,255,255,0.75)" }}>Same-day dispatch · Free delivery above ₹500 · Use code <strong style={{fontFamily:"var(--mono)",color:"#81c784"}}>CROPAI10</strong></div>
          </div>
        </div>
        <button onClick={onMedicines} style={{ background:"rgba(255,255,255,0.15)", border:"1px solid rgba(255,255,255,0.3)", color:"#fff", padding:"9px 20px", borderRadius:8, cursor:"pointer", fontFamily:"var(--body)", fontWeight:600, fontSize:13 }}>Shop Now →</button>
      </div>

      {/* FLASH SALE GRID */}
      <div style={{ padding:"60px 5%", background:"var(--bg2)" }}>
        <div style={{ display:"flex", alignItems:"flex-end", justifyContent:"space-between", marginBottom:28, flexWrap:"wrap", gap:12 }}>
          <div>
            <div style={{ fontSize:11, fontWeight:700, letterSpacing:3, textTransform:"uppercase", color:"#dc2626", marginBottom:8 }}>⚡ Flash Sale</div>
            <h2 style={{ fontFamily:"var(--display)", fontSize:"clamp(1.4rem,3vw,1.9rem)", fontWeight:800, letterSpacing:"-0.5px" }}>Budget treatments that work</h2>
          </div>
          <button className="btn btn-ghost" onClick={onMedicines} style={{ fontSize:13 }}>See all →</button>
        </div>
        <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill,minmax(260px,1fr))", gap:16 }}>
          {flashSaleMeds.map(med=><MedicineCard key={med.id} med={med} onBuy={window._openBuy} onAddCart={cart.add} compact />)}
        </div>
      </div>

      {/* PROMOTED FEATURED */}
      <div style={{ padding:"60px 5%", background:"var(--bg)" }}>
        <div style={{ display:"flex", alignItems:"flex-end", justifyContent:"space-between", marginBottom:28, flexWrap:"wrap", gap:12 }}>
          <div>
            <div style={{ fontSize:11, fontWeight:700, letterSpacing:3, textTransform:"uppercase", color:"var(--green)", marginBottom:8 }}>Featured Products</div>
            <h2 style={{ fontFamily:"var(--display)", fontSize:"clamp(1.4rem,3vw,1.9rem)", fontWeight:800, letterSpacing:"-0.5px" }}>Top-rated crop treatments</h2>
            <p style={{ fontSize:13, color:"var(--text2)", marginTop:6, fontWeight:300 }}>Highest effectiveness · Best reviewed · Most recommended by CropAI</p>
          </div>
          <button className="btn btn-ghost" onClick={onMedicines} style={{ fontSize:13 }}>See all 12 →</button>
        </div>
        <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill,minmax(280px,1fr))", gap:20 }}>
          {promotedMeds.map(med=><MedicineCard key={med.id} med={med} onBuy={window._openBuy} onAddCart={cart.add} />)}
        </div>
      </div>

      {/* HOW IT WORKS */}
      <div style={{ padding:"80px 5%", background:"var(--bg2)" }}>
        <div style={{ textAlign:"center", marginBottom:50 }}>
          <div style={{ fontSize:11, fontWeight:700, letterSpacing:3, textTransform:"uppercase", color:"var(--green)", marginBottom:12 }}>The Pipeline</div>
          <h2 style={{ fontFamily:"var(--display)", fontSize:"clamp(1.6rem,3vw,2.2rem)", fontWeight:800, letterSpacing:"-1px" }}>Detect. Diagnose. Buy the cure.</h2>
        </div>
        <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))", gap:20, maxWidth:1000, margin:"0 auto" }}>
          {[{n:"01",icon:"📸",title:"Upload photo",desc:"Clear leaf photo, natural light."},{n:"02",icon:"🎯",title:"YOLO detects",desc:"Leaf region isolated precisely."},{n:"03",icon:"🔬",title:"ResNet classifies",desc:"Disease predicted with confidence."},{n:"04",icon:"🌡️",title:"Grad-CAM explains",desc:"Heatmap shows exactly why."},{n:"05",icon:"💊",title:"Buy medicine",desc:"Right treatment, delivered fast."}].map((s,i)=>(
            <div key={i} className="card" style={{ padding:22, textAlign:"center" }}>
              <div style={{ fontFamily:"var(--mono)", fontSize:11, color:"var(--green)", fontWeight:700, marginBottom:10 }}>{s.n}</div>
              <div style={{ fontSize:"1.8rem", marginBottom:10 }}>{s.icon}</div>
              <div style={{ fontWeight:700, fontSize:"0.9rem", marginBottom:6 }}>{s.title}</div>
              <div style={{ fontSize:12, color:"var(--text2)", lineHeight:1.6 }}>{s.desc}</div>
            </div>
          ))}
        </div>
      </div>

      <footer style={{ padding:"32px 5%", borderTop:"1px solid var(--border)", textAlign:"center", color:"var(--text3)", fontSize:13 }}>
        CropAI — YOLO + ResNet18 + Grad-CAM &nbsp;·&nbsp; *Accuracy on PlantVillage validation set
      </footer>
    </div>
  );
}

// ─── PAGE: DETECT ──────────────────────────────────────────────────────────────
const STEPS = [
  {label:"Validating leaf...",            icon:"🍃",detail:"Checking green pixel ratio"},
  {label:"YOLO detecting leaf region...", icon:"🎯",detail:"Isolating leaf from background"},
  {label:"ResNet classifying disease...", icon:"🔬",detail:"Running neural network inference"},
  {label:"Generating Grad-CAM...",        icon:"🌡️",detail:"Computing activation heatmap"},
  {label:"Building treatment plan...",    icon:"💊",detail:"Matching disease database"}
];

// ── Camera sub-component ──
function CameraCapture({ onCapture, onError }) {
  const videoRef  = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const [camReady,    setCamReady]    = useState(false);
  const [camError,    setCamError]    = useState(null);
  const [facingMode,  setFacingMode]  = useState("environment"); // back cam default
  const [flash,       setFlash]       = useState(false);         // shutter flash fx
  const [torchOn,     setTorchOn]     = useState(false);
  const [zoom,        setZoom]        = useState(1);

  // Start / restart stream
  const startStream = useCallback(async (facing) => {
    // Stop existing stream first
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
    setCamReady(false);
    setCamError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: facing },
          width:  { ideal: 1280 },
          height: { ideal: 720 },
        },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.onloadedmetadata = () => {
          videoRef.current.play();
          setCamReady(true);
        };
      }
    } catch (err) {
      const msg = err.name === "NotAllowedError"
        ? "Camera access denied. Please allow camera permissions in your browser settings."
        : err.name === "NotFoundError"
        ? "No camera found on this device."
        : "Could not start camera: " + err.message;
      setCamError(msg);
      onError && onError(msg);
    }
  }, [onError]);

  useEffect(() => {
    startStream(facingMode);
    return () => {
      if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop());
    };
  }, [facingMode]);

  // Torch (where supported)
  useEffect(() => {
    if (!streamRef.current) return;
    const track = streamRef.current.getVideoTracks()[0];
    if (track && track.getCapabilities?.()?.torch) {
      track.applyConstraints({ advanced: [{ torch: torchOn }] }).catch(() => {});
    }
  }, [torchOn]);

  // Zoom (where supported)
  useEffect(() => {
    if (!streamRef.current) return;
    const track = streamRef.current.getVideoTracks()[0];
    if (track && track.getCapabilities?.()?.zoom) {
      track.applyConstraints({ advanced: [{ zoom }] }).catch(() => {});
    }
  }, [zoom]);

  const capture = () => {
    if (!camReady || !videoRef.current || !canvasRef.current) return;
    const video  = videoRef.current;
    const canvas = canvasRef.current;
    canvas.width  = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    // shutter flash effect
    setFlash(true);
    setTimeout(() => setFlash(false), 200);
    canvas.toBlob(blob => {
      if (!blob) return;
      const file = new File([blob], "camera-capture.jpg", { type: "image/jpeg" });
      const url  = URL.createObjectURL(blob);
      onCapture(file, url);
    }, "image/jpeg", 0.92);
  };

  const flipCamera = () => setFacingMode(f => f === "environment" ? "user" : "environment");

  return (
    <div style={{ position:"relative", borderRadius:16, overflow:"hidden", background:"#0a0f0a", border:"2px solid var(--border)", minHeight:280 }}>
      {/* Viewfinder */}
      <video ref={videoRef} playsInline muted
        style={{ width:"100%", display:"block", maxHeight:320, objectFit:"cover", opacity:camReady?1:0, transition:"opacity .4s" }} />
      <canvas ref={canvasRef} style={{ display:"none" }} />

      {/* Shutter flash */}
      {flash && <div style={{ position:"absolute", inset:0, background:"#fff", opacity:0.7, pointerEvents:"none", animation:"flashFade 0.2s forwards" }} />}

      {/* Crosshair overlay */}
      {camReady && (
        <div style={{ position:"absolute", inset:0, pointerEvents:"none", display:"flex", alignItems:"center", justifyContent:"center" }}>
          <svg width="120" height="120" viewBox="0 0 120 120" fill="none">
            {/* Corner brackets */}
            <path d="M10 30 L10 10 L30 10"  stroke="rgba(76,175,80,0.85)" strokeWidth="2.5" strokeLinecap="round"/>
            <path d="M90 10 L110 10 L110 30" stroke="rgba(76,175,80,0.85)" strokeWidth="2.5" strokeLinecap="round"/>
            <path d="M10 90 L10 110 L30 110" stroke="rgba(76,175,80,0.85)" strokeWidth="2.5" strokeLinecap="round"/>
            <path d="M110 90 L110 110 L90 110" stroke="rgba(76,175,80,0.85)" strokeWidth="2.5" strokeLinecap="round"/>
            {/* Centre dot */}
            <circle cx="60" cy="60" r="2.5" fill="rgba(76,175,80,0.7)" />
          </svg>
        </div>
      )}

      {/* Loading spinner while cam warms up */}
      {!camReady && !camError && (
        <div style={{ position:"absolute", inset:0, display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", gap:12, color:"rgba(255,255,255,0.7)", fontSize:13 }}>
          <div style={{ width:28, height:28, borderRadius:"50%", border:"2.5px solid rgba(76,175,80,0.4)", borderTopColor:"#4caf50", animation:"spin 0.9s linear infinite" }} />
          Starting camera…
        </div>
      )}

      {/* Camera error */}
      {camError && (
        <div style={{ position:"absolute", inset:0, display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", padding:24, textAlign:"center", gap:12 }}>
          <div style={{ fontSize:"2rem" }}>📷</div>
          <div style={{ fontSize:13, color:"rgba(255,255,255,0.7)", lineHeight:1.6 }}>{camError}</div>
          <button onClick={()=>startStream(facingMode)} style={{ padding:"7px 18px", borderRadius:8, background:"var(--green)", color:"#fff", border:"none", cursor:"pointer", fontSize:13, fontFamily:"var(--body)", fontWeight:600 }}>Retry</button>
        </div>
      )}

      {/* Top controls: torch + flip */}
      {camReady && (
        <div style={{ position:"absolute", top:10, right:10, display:"flex", gap:6 }}>
          <button title="Flip camera" onClick={flipCamera}
            style={{ width:34, height:34, borderRadius:"50%", background:"rgba(0,0,0,0.5)", border:"1px solid rgba(255,255,255,0.2)", color:"#fff", cursor:"pointer", fontSize:15, display:"flex", alignItems:"center", justifyContent:"center", backdropFilter:"blur(4px)" }}>
            🔄
          </button>
          <button title={torchOn?"Torch off":"Torch on"} onClick={()=>setTorchOn(t=>!t)}
            style={{ width:34, height:34, borderRadius:"50%", background:torchOn?"rgba(255,214,0,0.3)":"rgba(0,0,0,0.5)", border:`1px solid ${torchOn?"rgba(255,214,0,0.6)":"rgba(255,255,255,0.2)"}`, color:torchOn?"#ffd600":"#fff", cursor:"pointer", fontSize:15, display:"flex", alignItems:"center", justifyContent:"center", backdropFilter:"blur(4px)" }}>
            🔦
          </button>
        </div>
      )}

      {/* Zoom slider */}
      {camReady && (
        <div style={{ position:"absolute", bottom:56, left:"50%", transform:"translateX(-50%)", display:"flex", alignItems:"center", gap:8, background:"rgba(0,0,0,0.45)", borderRadius:20, padding:"5px 14px", backdropFilter:"blur(6px)" }}>
          <span style={{ fontSize:11, color:"rgba(255,255,255,0.6)", fontFamily:"var(--mono)" }}>1×</span>
          <input type="range" min={1} max={3} step={0.1} value={zoom} onChange={e=>setZoom(Number(e.target.value))}
            style={{ width:80, accentColor:"#4caf50", cursor:"pointer" }} />
          <span style={{ fontSize:11, color:"rgba(255,255,255,0.6)", fontFamily:"var(--mono)" }}>{zoom.toFixed(1)}×</span>
        </div>
      )}

      {/* Shutter button */}
      {camReady && (
        <button onClick={capture}
          style={{ position:"absolute", bottom:10, left:"50%", transform:"translateX(-50%)", width:52, height:52, borderRadius:"50%", background:"#fff", border:"3px solid rgba(76,175,80,0.8)", cursor:"pointer", display:"flex", alignItems:"center", justifyContent:"center", boxShadow:"0 2px 16px rgba(0,0,0,0.4)", transition:"transform .1s", fontSize:20 }}
          onMouseDown={e=>e.currentTarget.style.transform="translateX(-50%) scale(0.9)"}
          onMouseUp={e=>e.currentTarget.style.transform="translateX(-50%) scale(1)"}>
          <div style={{ width:34, height:34, borderRadius:"50%", background:"var(--green)" }} />
        </button>
      )}
    </div>
  );
}

function DetectPage({ onResult }) {
  const [crop,setCrop]         = useState("tomato");
  const [inputMode,setInputMode] = useState("upload"); // "upload" | "camera"
  const [preview,setPreview]   = useState(null);
  const [file,setFile]         = useState(null);
  const [loading,setLoading]   = useState(false);
  const [step,setStep]         = useState(0);
  const [error,setError]       = useState(null);
  const [dragOver,setDragOver] = useState(false);
  const fileRef = useRef();

  const handleFile = (f) => {
    if (!f || !f.type.startsWith("image/")) { setError("Please upload an image file."); return; }
    setFile(f); setPreview(URL.createObjectURL(f)); setError(null);
  };
  const handleDrop = useCallback((e) => { e.preventDefault(); setDragOver(false); handleFile(e.dataTransfer.files[0]); }, []);

  const handleCameraCapture = (capturedFile, previewUrl) => {
    setFile(capturedFile);
    setPreview(previewUrl);
    setError(null);
    // auto-switch to review mode after capture
    setInputMode("upload");
  };

  const clearImage = () => { setPreview(null); setFile(null); setError(null); };

  const analyse = async () => {
    if (!file) return;
    setLoading(true); setError(null); setStep(0);
    try {
      for (let i = 0; i < STEPS.length; i++) { setStep(i); await new Promise(r => setTimeout(r, 600)); }
      const result = await runDetection(file, crop);
      if (result.status === "error" || result.status === "rejected") {
        setError(result.message || "Detection failed.");
        setLoading(false); return;
      }
      onResult(result);
    } catch (e) { setError(e.message || "Network error. Is the backend running?"); setLoading(false); }
  };

  const progress = loading ? Math.round(((step + 1) / STEPS.length) * 100) : 0;

  return (
    <div style={{ maxWidth:960, margin:"0 auto", padding:"60px 5%" }}>
      {/* Page heading */}
      <div className="fade-up" style={{ marginBottom:40 }}>
        <div style={{ fontSize:11, fontWeight:700, letterSpacing:3, textTransform:"uppercase", color:"var(--green)", marginBottom:10 }}>Step 1 of 2</div>
        <h1 style={{ fontFamily:"var(--display)", fontSize:"clamp(2rem,4vw,2.8rem)", fontWeight:800, letterSpacing:"-1.5px", marginBottom:10 }}>
          {inputMode === "camera" ? "Point at Leaf" : "Upload Leaf Photo"}
        </h1>
        <p style={{ color:"var(--text2)", fontSize:"1rem", fontWeight:300 }}>
          {inputMode === "camera"
            ? "Point at the affected leaf and tap the shutter button to capture."
            : "Select your crop, then drag a clear photo of the affected leaf."}
        </p>
      </div>

      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:32, alignItems:"start" }}>
        {/* LEFT PANEL */}
        <div>
          {/* Crop selector — 10 crops in grouped grid */}
          <div style={{ marginBottom:16 }}>
            <label style={{ fontSize:13, fontWeight:600, color:"var(--text2)", display:"block", marginBottom:10 }}>SELECT CROP</label>
            <div style={{ background:"var(--bg2)", borderRadius:12, border:"1px solid var(--border)", padding:"12px" }}>
              {CROP_GROUPS.map(group => (
                <div key={group.label} style={{ marginBottom:10 }}>
                  <div style={{ fontSize:9, fontWeight:700, letterSpacing:2, textTransform:"uppercase", color:"var(--text3)", marginBottom:6 }}>
                    {group.label}
                  </div>
                  <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill,minmax(74px,1fr))", gap:6 }}>
                    {group.crops.map(c => (
                      <button key={c.key} onClick={() => setCrop(c.key)}
                        style={{ padding:"8px 4px", borderRadius:8, cursor:"pointer", textAlign:"center",
                          border:`2px solid ${crop===c.key?"var(--green)":"var(--border)"}`,
                          background:crop===c.key?"rgba(76,175,80,0.12)":"var(--bg)",
                          color:crop===c.key?"var(--green)":"var(--text2)",
                          fontFamily:"var(--body)", fontWeight:crop===c.key?700:400,
                          transition:"all .2s", fontSize:11 }}>
                        <div style={{ fontSize:"1.3rem", marginBottom:2 }}>{CROP_EMOJIS[c.key]}</div>
                        {c.name}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            {/* Selected crop info strip */}
            {(() => {
              const info = CROP_GROUPS.flatMap(g=>g.crops).find(c=>c.key===crop);
              return info ? (
                <div style={{ marginTop:8, padding:"6px 12px", borderRadius:8, background:"rgba(76,175,80,0.06)", border:"1px solid rgba(76,175,80,0.2)", fontSize:11, color:"var(--text3)" }}>
                  <strong style={{color:"var(--green)"}}>{CROP_EMOJIS[crop]} {info.name}</strong> — detects: {info.diseases}
                </div>
              ) : null;
            })()}
          </div>

          {/* Input mode toggle */}
          <div style={{ display:"flex", gap:6, marginBottom:16 }}>
            {[
              { key:"upload", icon:"📁", label:"Upload Photo" },
              { key:"camera", icon:"📸", label:"Live Camera" },
            ].map(m => (
              <button key={m.key} onClick={() => { setInputMode(m.key); clearImage(); }}
                style={{ flex:1, display:"flex", alignItems:"center", justifyContent:"center", gap:7, padding:"10px 14px", borderRadius:10, fontSize:13, fontWeight:600, cursor:"pointer", fontFamily:"var(--body)", background:inputMode===m.key?"var(--green)":"var(--bg2)", color:inputMode===m.key?"#fff":"var(--text2)", border:`1.5px solid ${inputMode===m.key?"var(--green)":"var(--border)"}`, transition:"all .2s" }}>
                {m.icon} {m.label}
              </button>
            ))}
          </div>

          {/* ── UPLOAD MODE ── */}
          {inputMode === "upload" && (
            <>
              <div
                onClick={() => !loading && fileRef.current.click()}
                onDrop={handleDrop}
                onDragOver={e => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                style={{ border:`2px dashed ${dragOver?"var(--green)":preview?"rgba(76,175,80,0.4)":"var(--border)"}`, borderRadius:16, padding:"2rem", background:dragOver?"rgba(76,175,80,0.05)":"var(--bg2)", cursor:loading?"not-allowed":"pointer", transition:"all .25s", textAlign:"center", minHeight:220, display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center" }}>
                <input ref={fileRef} type="file" accept="image/*" style={{display:"none"}} onChange={e => handleFile(e.target.files[0])} />
                {preview
                  ? <img src={preview} alt="preview" style={{ maxHeight:240, maxWidth:"100%", borderRadius:10, objectFit:"contain" }} />
                  : <>
                      <div style={{fontSize:"3rem",marginBottom:12}}>📷</div>
                      <div style={{fontWeight:600,fontSize:"0.95rem",marginBottom:6}}>{dragOver?"Drop it!":"Drag photo here or click to upload"}</div>
                      <div style={{fontSize:12,color:"var(--text3)"}}>JPG, PNG, WebP supported</div>
                    </>
                }
              </div>
              {preview && !loading && (
                <button className="btn btn-ghost" style={{marginTop:10,width:"100%",fontSize:13}} onClick={clearImage}>✕ Remove image</button>
              )}
            </>
          )}

          {/* ── CAMERA MODE ── */}
          {inputMode === "camera" && !preview && (
            <CameraCapture onCapture={handleCameraCapture} onError={msg => setError(msg)} />
          )}

          {/* Camera captured preview */}
          {inputMode === "camera" && preview && (
            <div style={{ position:"relative", borderRadius:16, overflow:"hidden", border:"2px solid rgba(76,175,80,0.4)" }}>
              <img src={preview} alt="captured" style={{ width:"100%", display:"block", maxHeight:280, objectFit:"cover" }} />
              <div style={{ position:"absolute", top:10, left:10, background:"rgba(45,122,49,0.9)", color:"#fff", fontSize:11, fontWeight:700, padding:"3px 10px", borderRadius:20, letterSpacing:0.5 }}>
                ✓ Captured
              </div>
              <div style={{ position:"absolute", bottom:0, left:0, right:0, padding:"10px 14px", background:"linear-gradient(0deg,rgba(0,0,0,0.55),transparent)", display:"flex", justifyContent:"flex-end", gap:8 }}>
                <button onClick={() => { clearImage(); }}
                  style={{ padding:"6px 14px", borderRadius:8, background:"rgba(255,255,255,0.15)", border:"1px solid rgba(255,255,255,0.3)", color:"#fff", cursor:"pointer", fontSize:12, fontFamily:"var(--body)", backdropFilter:"blur(4px)" }}>
                  🔄 Retake
                </button>
              </div>
            </div>
          )}

          {/* Error */}
          {error && (
            <div style={{marginTop:14,padding:"14px 16px",borderRadius:10,background:"rgba(220,38,38,0.08)",border:"1px solid rgba(220,38,38,0.25)",color:"#dc2626",fontSize:13,lineHeight:1.7}}>
              <div style={{fontWeight:700,marginBottom:error.includes("\n")?8:0}}>⚠️ {error.split("\n")[0]}</div>
              {error.includes("\n") && (
                <ul style={{margin:"6px 0 0 4px",padding:0,listStyle:"none"}}>
                  {error.split("\n").slice(1).filter(Boolean).map((line,i)=>(
                    <li key={i} style={{fontSize:12,color:"#b91c1c",marginTop:3}}>{line}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* Camera tips */}
          {inputMode === "camera" && !preview && (
            <div style={{ marginTop:12, padding:"11px 14px", borderRadius:10, background:"rgba(76,175,80,0.06)", border:"1px solid rgba(76,175,80,0.18)", fontSize:12, color:"var(--text2)", lineHeight:1.7 }}>
              <strong style={{color:"var(--green)"}}>Tips for best results: </strong>
              Hold 10–20 cm from leaf · Use natural daylight · Keep steady before tapping shutter · Fill the frame
            </div>
          )}
        </div>

        {/* RIGHT PANEL — pipeline + analyse button */}
        <div>
          <div className="card" style={{ padding:28 }}>
            <div style={{ fontSize:13, fontWeight:600, color:"var(--text2)", marginBottom:20, letterSpacing:1 }}>AI PIPELINE</div>
            {STEPS.map((s,i) => (
              <div key={i} style={{ display:"flex", alignItems:"center", gap:12, marginBottom:14, opacity:loading?(i<=step?1:0.35):1, transition:"opacity .3s" }}>
                <div style={{ width:36, height:36, borderRadius:"50%", flexShrink:0, background:loading&&i<=step?"rgba(76,175,80,0.15)":"var(--bg3)", border:`1.5px solid ${loading&&i<=step?"var(--green)":"var(--border)"}`, display:"flex", alignItems:"center", justifyContent:"center", fontSize:"0.9rem", transition:"all .3s" }}>
                  {loading && i < step ? "✓" : s.icon}
                </div>
                <div style={{ flex:1 }}>
                  <div style={{ fontSize:13, fontWeight:600, color:loading&&i<=step?"var(--text)":"var(--text3)" }}>{s.label}</div>
                  <div style={{ fontSize:11, color:"var(--text3)", marginTop:2 }}>{s.detail}</div>
                </div>
                {loading && i === step && <div style={{ width:14, height:14, borderRadius:"50%", border:"2px solid var(--green)", borderTopColor:"transparent", animation:"spin 0.8s linear infinite" }} />}
              </div>
            ))}
            {loading && (
              <div style={{ marginTop:20 }}>
                <div style={{ display:"flex", justifyContent:"space-between", fontSize:12, marginBottom:6, color:"var(--text3)" }}>
                  <span>Analysing...</span><span style={{fontFamily:"var(--mono)",color:"var(--green)"}}>{progress}%</span>
                </div>
                <div style={{ height:4, background:"var(--border-bg)", borderRadius:2 }}>
                  <div style={{ height:"100%", borderRadius:2, background:"linear-gradient(90deg,#4caf50,#81c784)", width:`${progress}%`, transition:"width .4s" }} />
                </div>
              </div>
            )}
          </div>

          {/* Source badge under pipeline */}
          {file && !loading && (
            <div style={{ marginTop:10, padding:"8px 14px", borderRadius:8, background:"rgba(76,175,80,0.07)", border:"1px solid rgba(76,175,80,0.2)", fontSize:12, color:"var(--text2)", display:"flex", alignItems:"center", gap:8 }}>
              <span>{inputMode==="camera"?"📸":"📁"}</span>
              <span><strong style={{color:"var(--green)"}}>{inputMode==="camera"?"Camera capture":"File upload"}</strong> ready to analyse</span>
            </div>
          )}

          <button className="btn btn-primary" disabled={!file||loading} onClick={analyse}
            style={{ width:"100%", marginTop:12, padding:"15px", fontSize:"1rem", fontWeight:700, opacity:(!file||loading)?0.5:1, cursor:(!file||loading)?"not-allowed":"pointer" }}>
            {loading ? "Analysing leaf…" : `🔬 Analyse ${crop.charAt(0).toUpperCase()+crop.slice(1)} Leaf`}
          </button>
          <div style={{ marginTop:12, fontSize:12, color:"var(--text3)", textAlign:"center", lineHeight:1.6 }}>
            {inputMode==="camera" ? "Capture leaf · tap shutter · analyse" : "Natural light · fill frame · keep in focus"}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── PAGE: RESULT ──────────────────────────────────────────────────────────────
function ResultPage({ result, onBack, onNewScan, onMedicines, onBuy, cart }) {
  const [imgMode,setImgMode]=useState("original");
  const [remedyTab,setRemedyTab]=useState("organic");

  // ── Normalise disease name: "Leaf_Curl" → "Curl Virus", "Bacterial_Blight" → "Bacterial Blight"
  // Model folder names may use underscores; map them to the DISEASE_INFO space-key
  function normaliseDisease(raw) {
    if (!raw) return raw;
    const withSpaces = raw.replace(/_/g, " ").trim();
    // Direct match first
    if (DISEASE_INFO[withSpaces]) return withSpaces;
    // Case-insensitive fallback
    const lower = withSpaces.toLowerCase();
    const found = Object.keys(DISEASE_INFO).find(k => k.toLowerCase() === lower);
    return found || withSpaces;
  }

  const disease = normaliseDisease(result.disease);
  const info    = DISEASE_INFO[disease] || {};
  const remedies= info.remedies || {};
  const tabs    = Object.keys(remedies);
  const curTab  = remedies[remedyTab] ? remedyTab : (tabs[0] || "organic");
  const imgSrc  = imgMode==="gradcam"
    ? `data:image/jpeg;base64,${result.grad_cam}`
    : imgMode==="boxed"
      ? `data:image/jpeg;base64,${result.boxed_image}`
      : null;
  const diseaseMeds = (DISEASE_MEDICINES[disease]||[]).map(id=>MEDICINES.find(m=>m.id===id)).filter(Boolean);
  const isSevere    = DISEASE_INFO[disease]?.severity === "severe";

  return (
    <div style={{ maxWidth:1100, margin:"0 auto", padding:"clamp(20px,5vw,60px) clamp(12px,5%,48px)" }}>

      {/* ── Header ─────────────────────────────────────────────── */}
      <div className="fade-up" style={{ display:"flex", alignItems:"flex-start", justifyContent:"space-between", marginBottom:"clamp(20px,4vw,40px)", gap:16, flexWrap:"wrap" }}>
        <div>
          <button onClick={onBack} style={{ background:"none", border:"1px solid var(--border)", color:"var(--text2)", padding:"6px 14px", borderRadius:8, cursor:"pointer", fontFamily:"var(--body)", fontSize:13, marginBottom:14 }}>← Back</button>
          <div style={{ display:"flex", alignItems:"center", gap:12, marginBottom:8, flexWrap:"wrap" }}>
            <span style={{fontSize:"clamp(1.5rem,4vw,2rem)"}}>{CROP_EMOJIS[result.crop?.toLowerCase()]||"🌿"}</span>
            <h1 style={{ fontFamily:"var(--display)", fontSize:"clamp(1.5rem,5vw,2.6rem)", fontWeight:800, letterSpacing:"-1px", lineHeight:1.1 }}>{disease}</h1>
          </div>
          <div style={{ display:"flex", gap:10, flexWrap:"wrap", alignItems:"center" }}>
            <SeverityBadge disease={disease} />
            <span style={{ fontFamily:"var(--mono)", fontWeight:700, fontSize:14, color:result.confidence>80?"var(--green)":"#ca8a04" }}>{result.confidence.toFixed(1)}% confidence</span>
            <span style={{ fontSize:13, color:"var(--text3)" }}>· {result.crop}</span>
          </div>
        </div>
        <button className="btn btn-primary" onClick={onNewScan} style={{ whiteSpace:"nowrap", flexShrink:0 }}>+ New Scan</button>
      </div>

      {/* ── Two-column grid (stacks on mobile) ─────────────────── */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(min(100%,320px),1fr))", gap:"clamp(16px,3vw,32px)" }}>

        {/* ── LEFT: Image viewer + predictions ────────────────── */}
        <div className="fade-up" style={{ animationDelay:"0.1s" }}>
          {/* Image toggle buttons */}
          <div style={{ display:"flex", gap:6, marginBottom:14 }}>
            {[
              {key:"original", label:"📷 Original"},
              {key:"boxed",    label:"🎯 YOLO Box",  show:!!result.boxed_image},
              {key:"gradcam",  label:"🌡️ Grad-CAM",  show:!!result.grad_cam},
            ].filter(t=>t.show!==false).map(t=>(
              <button key={t.key} onClick={()=>setImgMode(t.key)}
                style={{ flex:1, padding:"8px 4px", borderRadius:8, fontSize:11, fontWeight:600, cursor:"pointer", fontFamily:"var(--body)",
                  background:imgMode===t.key?"var(--green)":"var(--bg2)",
                  color:imgMode===t.key?"#fff":"var(--text2)",
                  border:`1px solid ${imgMode===t.key?"var(--green)":"var(--border)"}`,
                  transition:"all .2s" }}>
                {t.label}
              </button>
            ))}
          </div>

          {/* Image box */}
          <div className="card" style={{ padding:0, overflow:"hidden", marginBottom:14 }}>
            {imgSrc
              ? <img src={imgSrc} alt={imgMode} style={{ width:"100%", display:"block", borderRadius:14 }} />
              : <div style={{ aspectRatio:"4/3", display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", background:"var(--bg2)", color:"var(--text3)", fontSize:13, padding:20, textAlign:"center" }}>
                  <div style={{fontSize:"2.5rem",marginBottom:10}}>{CROP_EMOJIS[result.crop?.toLowerCase()]||"🌿"}</div>
                  Select YOLO Box or Grad-CAM above
                </div>}
          </div>

          {imgMode==="gradcam" && (
            <div style={{ marginBottom:14, padding:"10px 14px", borderRadius:8, fontSize:12, lineHeight:1.6, background:"rgba(76,175,80,0.07)", border:"1px solid rgba(76,175,80,0.2)", color:"var(--text2)" }}>
              <strong style={{color:"var(--green)"}}>Grad-CAM:</strong> Warm colours (red/orange) show the infected regions the model focused on.
            </div>
          )}

          {/* Top predictions */}
          <div className="card" style={{ padding:22 }}>
            <div style={{ fontSize:11, fontWeight:700, marginBottom:16, color:"var(--text2)", letterSpacing:1, textTransform:"uppercase" }}>Top Predictions</div>
            {result.top_predictions?.map((p,i)=>(
              <ConfBar key={i}
                label={p.label.replace(/_/g," ")}
                value={p.confidence}
                color={i===0?"var(--green)":i===1?"#ca8a04":"#94a3b8"}
                delay={i*0.1} />
            ))}
          </div>
        </div>

        {/* ── RIGHT: Diagnosis + Treatment ────────────────────── */}
        <div className="fade-up" style={{ animationDelay:"0.15s", display:"flex", flexDirection:"column", gap:16 }}>

          {/* Healthy banner */}
          {result.is_healthy && (
            <div style={{ padding:"20px 22px", borderRadius:14, background:"rgba(22,163,74,0.08)", border:"1px solid rgba(22,163,74,0.25)" }}>
              <div style={{fontSize:"1.6rem",marginBottom:8}}>🎉</div>
              <div style={{fontWeight:700,color:"#16a34a",fontSize:"1rem",marginBottom:6}}>Your crop looks healthy!</div>
              <div style={{fontSize:13,color:"var(--text2)",lineHeight:1.6}}>No signs of disease detected. Continue current practices and monitor regularly.</div>
            </div>
          )}

          {/* Diagnosis card */}
          {info.description && (
            <div className="card" style={{ padding:22 }}>
              <div style={{ fontSize:11, fontWeight:700, color:"var(--text2)", letterSpacing:1, textTransform:"uppercase", marginBottom:14 }}>Diagnosis</div>
              <p style={{ fontSize:"0.88rem", color:"var(--text2)", lineHeight:1.8, marginBottom:14 }}>{info.description}</p>
              {info.causes && (
                <div style={{ fontSize:13, color:"var(--text3)", padding:"10px 14px", background:"var(--bg3)", borderRadius:8, borderLeft:"3px solid var(--green)", lineHeight:1.6 }}>
                  <strong style={{color:"var(--text2)"}}>Causes: </strong>{info.causes}
                </div>
              )}
            </div>
          )}

          {/* Treatment plan card */}
          {tabs.length > 0 && (
            <div className="card" style={{ padding:22 }}>
              <div style={{ fontSize:11, fontWeight:700, color:"var(--text2)", letterSpacing:1, textTransform:"uppercase", marginBottom:16 }}>Treatment Plan</div>
              {/* Tab row */}
              <div style={{ display:"flex", gap:6, marginBottom:18, flexWrap:"wrap" }}>
                {tabs.map(t=>(
                  <button key={t} onClick={()=>setRemedyTab(t)}
                    style={{ padding:"7px 16px", borderRadius:8, fontSize:12, fontWeight:600, cursor:"pointer", fontFamily:"var(--body)",
                      background:curTab===t?"var(--green)":"var(--bg3)",
                      color:curTab===t?"#fff":"var(--text2)",
                      border:`1px solid ${curTab===t?"var(--green)":"var(--border)"}`,
                      transition:"all .2s", textTransform:"capitalize" }}>
                    {t==="organic"?"🌿 Organic":t==="chemical"?"⚗️ Chemical":"🛡️ Prevention"}
                  </button>
                ))}
              </div>
              {/* Remedy list */}
              <ul style={{ listStyle:"none", margin:0, padding:0 }}>
                {(remedies[curTab]||[]).map((r,i)=>(
                  <li key={i} style={{ display:"flex", gap:10, padding:"10px 0",
                    borderBottom:i<(remedies[curTab]||[]).length-1?"1px solid var(--border)":"none",
                    fontSize:"0.84rem", color:"var(--text2)", lineHeight:1.65 }}>
                    <span style={{color:"var(--green)",fontWeight:700,marginTop:2,flexShrink:0}}>→</span>
                    {r}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* No disease info fallback */}
          {!info.description && !result.is_healthy && (
            <div className="card" style={{ padding:22 }}>
              <div style={{ fontSize:11, fontWeight:700, color:"var(--text2)", letterSpacing:1, textTransform:"uppercase", marginBottom:10 }}>Diagnosis</div>
              <p style={{ fontSize:"0.88rem", color:"var(--text2)", lineHeight:1.8 }}>
                Disease <strong>{disease}</strong> detected with {result.confidence.toFixed(1)}% confidence.
                Please consult a local agricultural extension officer for treatment advice specific to your region.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* ══ RECOMMENDED MEDICINES ══ */}
      {diseaseMeds.length > 0 && (
        <div style={{ marginTop:"clamp(36px,5vw,72px)", paddingTop:"clamp(20px,4vw,40px)", borderTop:"2px solid var(--border)" }}>
          <div style={{ display:"flex", alignItems:"flex-end", justifyContent:"space-between", marginBottom:20, flexWrap:"wrap", gap:12 }}>
            <div>
              <div style={{ fontSize:11, fontWeight:700, letterSpacing:3, textTransform:"uppercase", color:"var(--green)", marginBottom:8 }}>
                {result.is_healthy ? "Preventive Care" : "Recommended Medicines"}
              </div>
              <h2 style={{ fontFamily:"var(--display)", fontSize:"clamp(1.2rem,3vw,2rem)", fontWeight:800, letterSpacing:"-0.5px" }}>
                {result.is_healthy ? "Keep your crop healthy 🌿" : `Best treatments for ${disease}`}
              </h2>
              {!result.is_healthy && (
                <p style={{ fontSize:13, color:"var(--text2)", marginTop:6 }}>
                  Matched to <strong>{disease}</strong> in {result.crop} · sorted by effectiveness
                </p>
              )}
            </div>
            <button className="btn btn-ghost" onClick={onMedicines} style={{ fontSize:13 }}>
              Browse all products →
            </button>
          </div>

          {isSevere && (
            <div style={{ padding:"14px 20px", borderRadius:10, marginBottom:20, background:"rgba(220,38,38,0.07)", border:"1px solid rgba(220,38,38,0.2)", display:"flex", gap:12, alignItems:"flex-start" }}>
              <span style={{fontSize:"1.3rem",flexShrink:0}}>⚠️</span>
              <div style={{ fontSize:13, color:"var(--text2)", lineHeight:1.5 }}>
                <strong style={{color:"#dc2626"}}>Severe disease detected.</strong> Begin treatment within 24–48 hours to prevent spread. Start with the highest-effectiveness product below.
              </div>
            </div>
          )}

          <div style={{ padding:"11px 18px", borderRadius:8, marginBottom:20, background:"rgba(76,175,80,0.06)", border:"1px solid rgba(76,175,80,0.2)", display:"flex", alignItems:"center", justifyContent:"space-between", flexWrap:"wrap", gap:10 }}>
            <div style={{ fontSize:13, color:"var(--text2)" }}>
              🎁 Code <strong style={{fontFamily:"var(--mono)",color:"var(--green)"}}>CROPAI10</strong> — 10% off first order · Free delivery above ₹500
            </div>
            <span style={{ fontSize:11, fontWeight:700, color:"var(--green)" }}>Limited time</span>
          </div>

          <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill,minmax(min(100%,280px),1fr))", gap:20 }}>
            {[...diseaseMeds].sort((a,b)=>b.effectiveness-a.effectiveness).slice(0,4).map(med=>(
              <MedicineCard key={med.id} med={med} onBuy={onBuy} onAddCart={cart.add} />
            ))}
          </div>

          {diseaseMeds.length > 4 && (
            <div style={{ textAlign:"center", marginTop:20 }}>
              <button className="btn btn-ghost" onClick={onMedicines} style={{ fontSize:13 }}>
                +{diseaseMeds.length-4} more options in Medicine Store →
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── PAGE: MEDICINES ──────────────────────────────────────────────────────────
function MedicinesPage({ onBuy, defaultDisease, cart }) {
  const [search,setSearch]     = useState("");
  const [filterType,setFT]     = useState("all");
  const [filterDisease,setFD]  = useState(defaultDisease||"all");
  const [filterCrop,setFC]     = useState("all");
  const [sortBy,setSortBy]     = useState("featured");
  const [view,setView]         = useState("grid");

  useEffect(()=>{ if(defaultDisease) setFD(defaultDisease); },[defaultDisease]);

  const allDiseases = [...new Set(MEDICINES.flatMap(m=>m.diseases))].sort();

  const filtered = MEDICINES.filter(m=>{
    const q=search.toLowerCase();
    return (!q||[m.name,m.brand,m.category,...m.diseases,...m.tags].some(s=>s.toLowerCase().includes(q)))
      &&(filterType==="all"||m.type===filterType||(filterType==="organic"&&m.type==="organic-approved"))
      &&(filterDisease==="all"||m.diseases.includes(filterDisease))
      &&(filterCrop==="all"||m.crops.includes(filterCrop));
  });

  const sorted = [...filtered].sort((a,b)=>{
    if(sortBy==="featured")      return (b.featured?1:0)-(a.featured?1:0)||(b.effectiveness-a.effectiveness);
    if(sortBy==="price_asc")     return a.price-b.price;
    if(sortBy==="price_desc")    return b.price-a.price;
    if(sortBy==="rating")        return b.rating-a.rating;
    if(sortBy==="effectiveness") return b.effectiveness-a.effectiveness;
    return 0;
  });

  const ss = { padding:"8px 12px", borderRadius:8, border:"1px solid var(--border)", background:"var(--bg)", color:"var(--text2)", fontFamily:"var(--body)", fontSize:13, cursor:"pointer", outline:"none" };
  const hasFilter = filterDisease!=="all"||filterType!=="all"||filterCrop!=="all"||search;

  const CAT_PILLS = [
    {label:"All Products",  type:"all",              disease:"all",          icon:"💊"},
    {label:"Fungicides",    type:"chemical",          disease:"all",          icon:"🍄"},
    {label:"Bactericides",  type:"all",               disease:"Bacterial Spot",icon:"🦠"},
    {label:"Organic",       type:"organic",           disease:"all",          icon:"🌿"},
    {label:"Budget < ₹200", type:"all",               disease:"all",          icon:"💰", maxPrice:200},
    {label:"Premium",       type:"all",               disease:"all",          icon:"⭐", minEffect:95},
  ];

  return (
    <div style={{ maxWidth:1200, margin:"0 auto", padding:"60px 5%" }}>
      {/* Header */}
      <div className="fade-up" style={{ marginBottom:36 }}>
        <div style={{ fontSize:11, fontWeight:700, letterSpacing:3, textTransform:"uppercase", color:"var(--green)", marginBottom:10 }}>Medicine Store</div>
        <h1 style={{ fontFamily:"var(--display)", fontSize:"clamp(2rem,4vw,2.8rem)", fontWeight:800, letterSpacing:"-1.5px", marginBottom:12 }}>Crop Treatment Products</h1>
        <p style={{ color:"var(--text2)", fontSize:"1rem", fontWeight:300, maxWidth:560 }}>12 fungicides, bactericides and organic solutions — each matched to a specific disease with exact dosage guidance.</p>
      </div>

      {/* Promo banner */}
      <div style={{ background:"linear-gradient(135deg,#1e5c21,#2d7a31)", borderRadius:16, padding:"22px 28px", marginBottom:36, display:"flex", alignItems:"center", justifyContent:"space-between", flexWrap:"wrap", gap:16 }}>
        <div style={{ display:"flex", gap:16, alignItems:"center" }}>
          <span style={{fontSize:"2rem"}}>🎁</span>
          <div>
            <div style={{ fontWeight:700, fontSize:"1.05rem", color:"#fff", marginBottom:3 }}>First order — 10% off + free delivery above ₹500</div>
            <div style={{ fontSize:13, color:"rgba(255,255,255,0.75)" }}>Code: <strong style={{fontFamily:"var(--mono)",color:"#81c784"}}>CROPAI10</strong> · Same-day dispatch · 7-day returns</div>
          </div>
        </div>
        <span style={{ fontSize:11, fontWeight:700, color:"#ffeb3b", background:"rgba(255,235,59,0.15)", padding:"5px 14px", borderRadius:20, border:"1px solid rgba(255,235,59,0.3)", whiteSpace:"nowrap" }}>⚡ Limited time</span>
      </div>

      {/* Category quick-access pills */}
      <div style={{ display:"flex", gap:8, flexWrap:"wrap", marginBottom:24 }}>
        {CAT_PILLS.map((c,i)=>{
          let active = false;
          if(i===0) active=!hasFilter;
          else if(c.maxPrice) active=false;
          else if(c.minEffect) active=false;
          else active=(c.type!=="all"&&filterType===c.type)||(c.disease!=="all"&&filterDisease===c.disease);
          return (
            <button key={i} onClick={()=>{
              if(i===0){setFT("all");setFD("all");setFC("all");setSearch("");}
              else if(c.maxPrice) setSortBy("price_asc");
              else if(c.minEffect) setSortBy("effectiveness");
              else { if(c.type!=="all") setFT(c.type); if(c.disease!=="all") setFD(c.disease); }
            }}
              style={{ display:"inline-flex", alignItems:"center", gap:6, padding:"7px 16px", borderRadius:20, fontSize:13, fontWeight:600, cursor:"pointer", fontFamily:"var(--body)", background:active?"var(--green)":"var(--bg2)", color:active?"#fff":"var(--text2)", border:`1px solid ${active?"var(--green)":"var(--border)"}`, transition:"all .2s" }}>
              {c.icon} {c.label}
            </button>
          );
        })}
      </div>

      {/* Filters */}
      <div style={{ display:"flex", gap:10, flexWrap:"wrap", marginBottom:20, padding:"16px 18px", background:"var(--bg2)", borderRadius:12, border:"1px solid var(--border)", alignItems:"center" }}>
        <input placeholder="🔍  Search by name, disease, or tag..." value={search} onChange={e=>setSearch(e.target.value)} style={{ ...ss, flex:"1 1 200px", padding:"8px 14px" }} />
        <select value={filterDisease} onChange={e=>setFD(e.target.value)} style={ss}>
          <option value="all">All Diseases</option>
          {allDiseases.map(d=><option key={d} value={d}>{d}</option>)}
        </select>
        <select value={filterCrop} onChange={e=>setFC(e.target.value)} style={ss}>
          <option value="all">All Crops</option>
          <optgroup label="── Vegetables">
            <option value="tomato">🍅 Tomato</option>
            <option value="potato">🥔 Potato</option>
            <option value="pepper">🌶️ Pepper</option>
            <option value="onion">🧅 Onion</option>
          </optgroup>
          <optgroup label="── Fruits">
            <option value="mango">🥭 Mango</option>
            <option value="banana">🍌 Banana</option>
          </optgroup>
          <optgroup label="── Field Crops">
            <option value="rice">🌾 Rice</option>
            <option value="wheat">🌾 Wheat</option>
            <option value="sugarcane">🎋 Sugarcane</option>
            <option value="cotton">🌸 Cotton</option>
          </optgroup>
        </select>
        <select value={sortBy} onChange={e=>setSortBy(e.target.value)} style={ss}>
          <option value="featured">Featured</option>
          <option value="rating">Top Rated</option>
          <option value="effectiveness">Most Effective</option>
          <option value="price_asc">Price: Low–High</option>
          <option value="price_desc">Price: High–Low</option>
        </select>
        <div style={{ display:"flex", gap:4 }}>
          <button title="Grid view" onClick={()=>setView("grid")} style={{ padding:"7px 10px", borderRadius:7, background:view==="grid"?"var(--green)":"var(--bg)", color:view==="grid"?"#fff":"var(--text3)", border:`1px solid ${view==="grid"?"var(--green)":"var(--border)"}`, cursor:"pointer", fontSize:15 }}>⊞</button>
          <button title="List view" onClick={()=>setView("list")} style={{ padding:"7px 10px", borderRadius:7, background:view==="list"?"var(--green)":"var(--bg)", color:view==="list"?"#fff":"var(--text3)", border:`1px solid ${view==="list"?"var(--green)":"var(--border)"}`, cursor:"pointer", fontSize:15 }}>☰</button>
        </div>
        {hasFilter&&<button className="btn btn-ghost" style={{ fontSize:12, padding:"7px 14px" }} onClick={()=>{setSearch("");setFT("all");setFD("all");setFC("all");}}>✕ Clear</button>}
      </div>

      <div style={{ display:"flex", alignItems:"center", gap:16, marginBottom:20, flexWrap:"wrap" }}>
        <span style={{ fontSize:13, color:"var(--text3)" }}>
          Showing <strong style={{color:"var(--text)"}}>{sorted.length}</strong> of {MEDICINES.length} products
          {filterDisease!=="all"&&<span> · <strong style={{color:"var(--green)"}}>{filterDisease}</strong></span>}
          {filterCrop!=="all"&&<span> · <strong style={{color:"var(--green)"}}>{filterCrop}</strong></span>}
        </span>
        {sorted.some(m=>!m.inStock)&&<span style={{ fontSize:12, color:"#dc2626", background:"rgba(220,38,38,0.08)", padding:"3px 10px", borderRadius:6, border:"1px solid rgba(220,38,38,0.15)" }}>Some items out of stock</span>}
      </div>

      {sorted.length===0
        ?<div style={{ textAlign:"center", padding:"80px 20px", color:"var(--text3)" }}><div style={{fontSize:"3rem",marginBottom:12}}>🔍</div><div style={{fontWeight:600,marginBottom:6}}>No medicines found</div><div style={{fontSize:13}}>Try different filters.</div></div>
        :<div style={view==="grid"?{ display:"grid", gridTemplateColumns:"repeat(auto-fill,minmax(300px,1fr))", gap:22 }:{ display:"flex", flexDirection:"column", gap:12 }}>
          {sorted.map(med=><MedicineCard key={med.id} med={med} onBuy={onBuy} onAddCart={cart.add} compact={view==="list"} />)}
        </div>
      }

      <div style={{ marginTop:48, padding:"16px 20px", borderRadius:10, background:"var(--bg2)", border:"1px solid var(--border)", fontSize:12, color:"var(--text3)", lineHeight:1.7 }}>
        <strong style={{color:"var(--text2)"}}>⚠️ Disclaimer:</strong> Always follow label instructions and local agricultural guidelines. Wear PPE. Observe pre-harvest intervals (PHI). Consult a licensed agronomist for severe infestations. Prices are indicative.
      </div>
    </div>
  );
}

// ─── ROOT APP ─────────────────────────────────────────────────────────────────
export default function App() {
  const [page,setPage]     = useState("home");
  const [result,setResult] = useState(null);
  const [buyMed,setBuyMed] = useState(null);
  const [medFilter,setMF]  = useState(null);
  const [cartOpen,setCart] = useState(false);
  const [menuOpen,setMenu] = useState(false);
  const cart = useCart();

  window._openBuy = setBuyMed;

  const goMedicines = (disease=null) => { setMF(disease); setPage("medicines"); setMenu(false); };
  const goPage = (p) => { setPage(p); setMenu(false); };

  // Close menu on outside click
  const menuRef = useRef(null);
  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenu(false);
    };
    document.addEventListener("mousedown", handler);
    document.addEventListener("touchstart", handler);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("touchstart", handler);
    };
  }, [menuOpen]);

  // Lock body scroll when mobile menu is open
  useEffect(() => {
    document.body.style.overflow = menuOpen ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [menuOpen]);

  const NAV_LINKS = [
    { p:"home",      l:"Home",      icon:"🏠" },
    { p:"detect",    l:"Detect",    icon:"🔬" },
    { p:"medicines", l:"Medicines", icon:"💊" },
  ];

  return (
    <>
      {/* ── NAV ─────────────────────────────────────────────────────────────── */}
      <nav ref={menuRef} style={{
        position:"sticky", top:0, zIndex:300,
        background:"rgba(255,255,255,0.96)", backdropFilter:"blur(16px)",
        borderBottom:"1px solid var(--border)",
        padding:"0 clamp(14px,4%,40px)", height:60,
        display:"flex", alignItems:"center",
      }}>
        {/* Logo */}
        <button onClick={()=>goPage("home")} style={{
          background:"none", border:"none", cursor:"pointer",
          fontFamily:"var(--display)", fontSize:"clamp(1rem,4vw,1.2rem)",
          fontWeight:800, color:"var(--green)", letterSpacing:"-0.5px",
          flexShrink:0, padding:0,
        }}>🌿 CropAI</button>

        {/* ── DESKTOP links (hidden on mobile) ── */}
        <div style={{
          display:"flex", gap:"1.5rem", marginLeft:"auto", alignItems:"center",
        }} className="nav-desktop">
          {NAV_LINKS.map(({p,l})=>(
            <button key={p}
              onClick={()=>p==="medicines"?goMedicines():goPage(p)}
              style={{
                background:"none", border:"none", cursor:"pointer",
                fontFamily:"var(--body)", fontSize:"0.9rem",
                color:page===p?"var(--green)":"var(--text2)",
                fontWeight:page===p?600:400,
                borderBottom:page===p?"2px solid var(--green)":"2px solid transparent",
                paddingBottom:2, transition:"all .2s",
              }}>{l}</button>
          ))}
          {/* Cart */}
          <button onClick={()=>setCart(true)} style={{
            position:"relative",
            background:cart.count>0?"rgba(76,175,80,0.08)":"transparent",
            border:"1px solid var(--border)", borderRadius:8,
            padding:"7px 14px", cursor:"pointer", fontSize:14,
            display:"flex", alignItems:"center", gap:6,
            fontFamily:"var(--body)", color:"var(--text2)", transition:"all .2s",
          }}>
            🛒 Cart
            {cart.count>0&&<span style={{
              position:"absolute", top:-7, right:-7,
              background:"var(--green)", color:"#fff",
              fontSize:10, fontWeight:800, width:19, height:19,
              borderRadius:"50%", display:"flex", alignItems:"center", justifyContent:"center",
            }}>{cart.count}</span>}
          </button>
          <button className="btn btn-primary"
            onClick={()=>goPage("detect")}
            style={{ padding:"8px 20px", fontSize:"0.88rem" }}>
            Analyse Crop →
          </button>
        </div>

        {/* ── MOBILE right cluster (cart badge + hamburger) ── */}
        <div style={{
          marginLeft:"auto", display:"flex", alignItems:"center", gap:8,
        }} className="nav-mobile">
          {/* Cart icon */}
          <button onClick={()=>setCart(true)} aria-label="Open cart" style={{
            position:"relative",
            background:cart.count>0?"rgba(76,175,80,0.1)":"transparent",
            border:"1px solid var(--border)", borderRadius:8,
            padding:"7px 12px", cursor:"pointer", fontSize:16,
            display:"flex", alignItems:"center",
            color:"var(--text2)", transition:"all .2s",
          }}>
            🛒
            {cart.count>0&&<span style={{
              position:"absolute", top:-7, right:-7,
              background:"var(--green)", color:"#fff",
              fontSize:10, fontWeight:800, width:19, height:19,
              borderRadius:"50%", display:"flex", alignItems:"center", justifyContent:"center",
            }}>{cart.count}</span>}
          </button>

          {/* Hamburger / X button */}
          <button
            onClick={()=>setMenu(m=>!m)}
            aria-label={menuOpen?"Close menu":"Open menu"}
            aria-expanded={menuOpen}
            style={{
              background:"none", border:"1px solid var(--border)",
              borderRadius:8, width:42, height:42, cursor:"pointer",
              display:"flex", flexDirection:"column",
              alignItems:"center", justifyContent:"center", gap:5,
              padding:0, transition:"all .2s",
              background: menuOpen ? "rgba(76,175,80,0.08)" : "transparent",
            }}>
            {/* Three lines → X animation */}
            <span style={{
              display:"block", width:20, height:2, borderRadius:2,
              background:"var(--text2)",
              transform: menuOpen ? "translateY(7px) rotate(45deg)" : "none",
              transition:"transform .25s ease",
            }}/>
            <span style={{
              display:"block", width:20, height:2, borderRadius:2,
              background:"var(--text2)",
              opacity: menuOpen ? 0 : 1,
              transition:"opacity .15s ease",
            }}/>
            <span style={{
              display:"block", width:20, height:2, borderRadius:2,
              background:"var(--text2)",
              transform: menuOpen ? "translateY(-7px) rotate(-45deg)" : "none",
              transition:"transform .25s ease",
            }}/>
          </button>
        </div>
      </nav>

      {/* ── MOBILE MENU OVERLAY ─────────────────────────────────────────────── */}
      {/* Backdrop */}
      <div
        onClick={()=>setMenu(false)}
        style={{
          position:"fixed", inset:0, zIndex:290,
          background:"rgba(0,0,0,0.35)", backdropFilter:"blur(3px)",
          opacity: menuOpen ? 1 : 0,
          pointerEvents: menuOpen ? "all" : "none",
          transition:"opacity .25s ease",
        }}
      />

      {/* Slide-down panel */}
      <div style={{
        position:"fixed", top:60, left:0, right:0, zIndex:295,
        background:"#fff",
        borderBottom:"1px solid var(--border)",
        borderRadius:"0 0 20px 20px",
        boxShadow:"0 16px 48px rgba(30,80,30,0.14)",
        padding: menuOpen ? "16px clamp(14px,5%,32px) 24px" : "0 clamp(14px,5%,32px)",
        maxHeight: menuOpen ? "420px" : "0",
        overflow:"hidden",
        transition:"max-height .3s cubic-bezier(.4,0,.2,1), padding .3s ease",
      }}>
        {/* Nav links */}
        <div style={{ display:"flex", flexDirection:"column", gap:4, marginBottom:16 }}>
          {NAV_LINKS.map(({p,l,icon})=>(
            <button key={p}
              onClick={()=>p==="medicines"?goMedicines():goPage(p)}
              style={{
                display:"flex", alignItems:"center", gap:14,
                padding:"13px 16px", borderRadius:12, cursor:"pointer",
                border:"none", textAlign:"left", width:"100%",
                background: page===p ? "rgba(76,175,80,0.1)" : "transparent",
                color: page===p ? "var(--green)" : "var(--text)",
                fontFamily:"var(--body)", fontSize:"1rem",
                fontWeight: page===p ? 700 : 400,
                transition:"background .15s",
              }}>
              <span style={{ fontSize:"1.3rem", width:30, textAlign:"center" }}>{icon}</span>
              {l}
              {page===p && <span style={{
                marginLeft:"auto", width:6, height:6, borderRadius:"50%",
                background:"var(--green)", flexShrink:0,
              }}/>}
            </button>
          ))}
        </div>

        {/* Divider */}
        <div style={{ height:1, background:"var(--border)", marginBottom:16 }}/>

        {/* CTA row */}
        <div style={{ display:"flex", gap:10 }}>
          <button
            className="btn btn-primary"
            onClick={()=>goPage("detect")}
            style={{ flex:1, justifyContent:"center", fontSize:"0.95rem", padding:"13px 20px" }}>
            🔬 Analyse My Crop
          </button>
          <button
            onClick={()=>{ setCart(true); setMenu(false); }}
            style={{
              position:"relative", padding:"13px 18px",
              borderRadius:50, border:"1.5px solid var(--border2)",
              background: cart.count>0 ? "rgba(76,175,80,0.08)" : "transparent",
              cursor:"pointer", fontSize:"1.1rem",
              display:"flex", alignItems:"center", gap:6,
              color:"var(--text2)", fontFamily:"var(--body)",
            }}>
            🛒
            {cart.count>0 && (
              <>
                <span style={{ fontSize:13, fontWeight:600, color:"var(--green)" }}>
                  {cart.count}
                </span>
                <span style={{
                  position:"absolute", top:-6, right:-6,
                  background:"var(--green)", color:"#fff",
                  fontSize:9, fontWeight:800, width:17, height:17,
                  borderRadius:"50%", display:"flex", alignItems:"center", justifyContent:"center",
                }}>{cart.count}</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* ── PAGES ── */}
      <main>
        {page==="home"      && <HomePage onStart={()=>setPage("detect")} onMedicines={()=>goMedicines()} cart={cart} />}
        {page==="detect"    && <DetectPage onResult={r=>{setResult(r);setPage("result");}} />}
        {page==="result"    && result && <ResultPage result={result} onBack={()=>setPage("detect")} onNewScan={()=>{setResult(null);setPage("detect");}} onMedicines={()=>goMedicines(result.disease)} onBuy={setBuyMed} cart={cart} />}
        {page==="medicines" && <MedicinesPage onBuy={setBuyMed} defaultDisease={medFilter} cart={cart} />}
      </main>

      {/* ── OVERLAYS ── */}
      {buyMed && <BuyModal med={buyMed} onClose={()=>setBuyMed(null)} onAddCart={(m,q)=>cart.add(m,q)} />}
      {cartOpen && <CartDrawer cart={cart} onClose={()=>setCart(false)} />}
    </>
  );
}