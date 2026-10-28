"""
Perfect Palate - Nutrition estimation

The recipe dataset has no nutrition columns, so values are *estimated* from each
recipe's ingredient list:

  1. every ingredient line is parsed into (quantity, unit, name)
  2. the name is matched against the small ingredient table below
  3. the quantity is converted to grams (using per-ingredient cup / each / clove
     weights) and multiplied by the per-100 g values
  4. totals are divided by the recipe's (estimated) servings

Reference values are per 100 g of the raw / as-listed ingredient and follow the
USDA FoodData Central (SR Legacy) reference foods. They were typed in by hand and
checked for internal consistency (see test_enhancements.py: kcal must agree with
the protein / carb / fat figures), but they were not pulled live from the USDA
API. Cuts of meat, brands and cooking losses vary, so everything that leaves
this module is labelled an estimate and carries a coverage figure saying how
much of the ingredient list could be counted.
"""
import re

# --------------------------------------------------------------------------- #
# Ingredient table
#
#   aliases (comma separated) | kcal prot carb fat fiber sugar sodium_mg | units
#
# units are grams per: cup, each (one item), clove, can, slice, head, stick,
# bunch, tsp, tbsp ... tsp/tbsp default to cup/48 and cup/16.
# A line starting with "cooked" attaches an alternate "cooked / canned" row to
# the entry above it.
# --------------------------------------------------------------------------- #
_TABLE = """
# ---- grains, flours, baking ------------------------------------------------
all-purpose flour, plain flour, wheat flour, white flour, flour, self-raising flour, self raising flour, bread flour, cake flour | 364 10.3 76.3 1.0 2.7 0.3 2 | cup=125
whole wheat flour, wholemeal flour, atta, whole wheat | 340 13.2 72.0 2.5 10.7 0.4 2 | cup=120
maize flour, maize meal, cornmeal, corn meal, corn flour, unga, polenta, ugali flour | 361 6.9 76.9 3.9 7.3 0.6 7 | cup=122
millet flour, millet, wimbi, finger millet | 378 11.0 72.8 4.2 8.5 0.0 5 | cup=120
sorghum flour, sorghum, mtama | 339 11.3 74.6 3.3 6.3 0.0 6 | cup=120
rice, white rice, basmati rice, long grain rice, jasmine rice, pishori | 365 7.1 80.0 0.7 1.3 0.1 5 | cup=185
  cooked | 130 2.7 28.2 0.3 0.4 0.1 1 | cup=158
brown rice | 370 7.9 77.2 2.9 3.5 0.9 7 | cup=190
  cooked | 123 2.7 25.6 1.0 1.6 0.2 4 | cup=195
pasta, spaghetti, macaroni, penne, linguine, lingine, fettuccine, tagliatelle, fusilli | 371 13.0 74.7 1.5 3.2 2.7 6 | cup=100
  cooked | 158 5.8 30.9 0.9 1.8 0.6 1 | cup=140
rolled oats, oats, oatmeal, porridge oats | 379 13.2 67.7 6.5 10.1 1.0 6 | cup=81
quinoa | 368 14.1 64.2 6.1 7.0 0.0 5 | cup=170
  cooked | 120 4.4 21.3 1.9 2.8 0.9 7 | cup=185
bread | 265 9.4 49.2 3.2 2.7 5.0 491 | slice=30
bread crumbs, breadcrumbs | 395 13.4 72.0 5.3 4.5 6.2 732 | cup=108
cornstarch, corn starch, arrowroot flour | 381 0.3 91.3 0.1 0.9 0.0 9 | cup=128
baking powder | 53 0.0 27.7 0.0 0.2 0.0 10600 | tsp=4.6
baking soda, bicarbonate of soda, bicarbonate | 0 0.0 0.0 0.0 0.0 0.0 27360 | tsp=4.6
yeast, dry yeast, active dry yeast, instant yeast | 325 40.4 41.2 7.6 26.9 0.0 51 | tsp=3
sugar, white sugar, granulated sugar, caster sugar | 387 0.0 100.0 0.0 0.0 99.8 1 | cup=200
brown sugar | 380 0.1 98.1 0.0 0.0 97.0 28 | cup=220
icing sugar, powdered sugar, confectioners sugar | 389 0.0 99.8 0.0 0.0 97.8 2 | cup=120
honey | 304 0.3 82.4 0.0 0.2 82.1 4 | cup=339
maple syrup, syrup | 260 0.0 67.0 0.1 0.0 60.5 12 | cup=315
cocoa powder, cocoa | 228 19.6 57.9 13.7 33.2 1.8 21 | cup=86
chocolate chips, chocolate chip, chocolate, dark chocolate | 479 4.2 63.9 29.8 5.9 51.5 11 | cup=168
vanilla extract, vanilla essence, vanilla | 288 0.1 12.7 0.1 0.0 12.7 9 | tsp=4.2

# ---- dairy & eggs ----------------------------------------------------------
milk, whole milk, fresh milk, full cream milk, maziwa | 61 3.2 4.8 3.3 0.0 4.8 43 | cup=244
butter, margarine, blue band | 717 0.9 0.1 81.1 0.0 0.1 643 | cup=227 stick=113
ghee | 876 0.3 0.0 99.5 0.0 0.0 2 | cup=205
yogurt, yoghurt, plain yogurt, mala, maziwa lala | 61 3.5 4.7 3.3 0.0 4.7 46 | cup=245
greek yogurt, greek yoghurt | 97 9.0 4.0 5.0 0.0 4.0 35 | cup=245
cream, heavy cream, whipping cream, fresh cream, double cream, whipped cream | 340 2.8 2.7 36.1 0.0 2.7 27 | cup=238
sour cream | 198 3.2 4.6 19.4 0.0 3.4 31 | cup=230
cream cheese | 342 6.2 4.1 34.4 0.0 3.2 321 | cup=232
cheddar cheese, cheddar, cheese | 403 22.9 3.1 33.3 0.0 0.5 653 | cup=113 slice=28
mozzarella, mozzarella cheese | 300 22.2 2.2 22.4 0.0 1.0 627 | cup=112
parmesan cheese, parmesan, parmigiano | 431 38.5 4.1 28.6 0.0 0.9 1529 | cup=100
feta cheese, feta | 264 14.2 4.1 21.3 0.0 4.1 917 | cup=150
evaporated milk | 134 6.8 10.0 7.6 0.0 10.0 106 | cup=252
condensed milk, sweetened condensed milk | 321 7.9 54.4 8.7 0.0 54.4 127 | cup=306
buttermilk | 40 3.3 4.8 0.9 0.0 4.8 105 | cup=245
ice cream, vanilla ice cream | 207 3.5 23.6 11.0 0.7 21.2 80 | scoop=66 cup=132
coconut milk | 197 2.0 2.8 21.3 0.0 2.8 13 | cup=226 can=400
coconut cream | 330 3.6 6.7 34.7 2.2 6.0 4 | cup=296 can=400
egg, eggs | 143 12.6 0.7 9.5 0.0 0.4 142 | each=50
egg white | 52 10.9 0.7 0.2 0.0 0.7 166 | each=33
egg yolk | 322 15.9 3.6 26.5 0.0 0.6 48 | each=17

# ---- meat, fish ------------------------------------------------------------
beef, beef cubes, beef steak, steak, stewing beef, beef chunks, meat | 190 19.0 0.0 12.5 0.0 0.0 70 |
ground beef, minced beef, mince, beef mince, minced meat, minced beef | 215 18.6 0.0 15.0 0.0 0.0 66 |
chicken breast, chicken fillet | 120 22.5 0.0 2.6 0.0 0.0 45 | each=175
chicken thigh, chicken drumstick, drumstick | 211 16.7 0.0 15.3 0.0 0.0 84 | each=110
chicken, kienyeji chicken, whole chicken, chicken pieces | 215 18.6 0.0 15.1 0.0 0.0 70 | each=1400 cup=140
chicken liver, liver | 119 16.9 0.7 4.8 0.0 0.0 71 |
gizzard | 94 17.7 0.0 2.1 0.0 0.0 69 |
goat meat, goat, mbuzi | 109 20.6 0.0 2.3 0.0 0.0 82 |
lamb, mutton | 282 16.6 0.0 23.4 0.0 0.0 59 |
tilapia, fish, white fish, cod, fish fillet, nile perch, fillet | 96 20.1 0.0 1.7 0.0 0.0 52 | each=150
salmon | 208 20.4 0.0 13.4 0.0 0.0 59 | each=170
tuna | 116 25.5 0.0 0.8 0.0 0.0 247 | can=140
shrimp, prawn | 85 20.1 0.0 0.5 0.0 0.0 119 | cup=145

tofu, extra-firm tofu, firm tofu | 144 17.3 2.8 8.7 2.3 0.6 14 | cup=252
tortilla, tortilla wrap, wrap, whole wheat tortilla | 312 8.3 51.5 8.0 3.3 3.0 640 | each=45
chapati | 297 7.6 45.0 9.0 2.5 1.0 380 | each=70

# ---- legumes, nuts, seeds --------------------------------------------------
kidney bean, red bean, rosecoco, bean | 333 23.6 60.0 0.8 15.2 2.2 24 | cup=184
  cooked | 127 8.7 22.8 0.5 6.4 0.3 1 | cup=177 can=250
black bean, njahi | 341 21.6 62.4 1.4 15.5 2.1 5 | cup=194
  cooked | 132 8.9 23.7 0.5 8.7 0.3 1 | cup=172 can=250
lentil | 352 24.6 63.4 1.1 10.7 2.0 6 | cup=192
  cooked | 116 9.0 20.1 0.4 7.9 1.8 2 | cup=198
chickpea, garbanzo | 378 20.5 62.9 6.0 12.2 10.7 24 | cup=200
  cooked | 164 8.9 27.4 2.6 7.6 4.8 7 | cup=164 can=240
green gram, mung bean, ndengu | 347 23.9 62.6 1.2 16.3 6.6 15 | cup=202
  cooked | 105 7.0 19.2 0.4 7.6 2.0 2 | cup=202
cowpea, black-eyed pea, black eyed pea, kunde | 336 23.5 60.0 1.3 10.6 6.9 16 | cup=169
  cooked | 116 7.7 20.8 0.5 6.5 3.3 4 | cup=171
pigeon pea, mbaazi | 343 21.7 62.8 1.5 15.0 0.0 17 | cup=180
peanut butter | 588 25.1 20.0 50.4 6.0 9.2 429 | cup=258
peanut, groundnut, ground nut, njugu karanga | 567 25.8 16.1 49.2 8.5 4.7 18 | cup=146
walnut | 654 15.2 13.7 65.2 6.7 2.6 2 | cup=117
pecan | 691 9.2 13.9 72.0 9.6 4.0 0 | cup=109
cashew | 553 18.2 30.2 43.9 3.3 5.9 12 | cup=137
almond | 579 21.2 21.6 49.9 12.5 4.4 1 | cup=143
sesame seed | 573 17.7 23.4 49.7 11.8 0.3 11 | cup=144
desiccated coconut, dried coconut, coconut flake, shredded coconut | 660 6.9 23.7 64.5 16.3 7.4 20 | cup=93
coconut, grated coconut | 354 3.3 15.2 33.5 9.0 6.2 20 | cup=80

# ---- vegetables ------------------------------------------------------------
onion, red onion, white onion, yellow onion | 40 1.1 9.3 0.1 1.7 4.2 4 | cup=160 each=110
spring onion, green onion, scallion | 32 1.8 7.3 0.2 2.6 2.3 16 | cup=100 each=15 bunch=100
garlic powder | 331 16.6 72.7 0.7 9.0 2.4 60 | tsp=3.1
onion powder | 341 10.4 79.1 1.0 15.2 6.6 73 | tsp=2.4
garlic | 149 6.4 33.1 0.5 2.1 1.0 17 | clove=3 each=3 tsp=3 tbsp=9 head=40
ginger powder, ground ginger, dried ginger | 335 9.0 71.6 4.2 14.1 3.4 27 | tsp=1.8
ginger, fresh ginger | 80 1.8 17.8 0.8 2.0 1.7 13 | tsp=2 tbsp=6 each=20
cherry tomato | 18 0.9 3.9 0.2 1.2 2.6 5 | cup=149 each=17
tomato paste, tomato puree, tomato concentrate | 82 4.3 18.9 0.5 4.1 12.2 98 | cup=262
tomato, tomatoe | 18 0.9 3.9 0.2 1.2 2.6 5 | cup=180 each=120 can=400
carrot | 41 0.9 9.6 0.2 2.8 4.7 69 | cup=128 each=61
sweet potato, viazi vitamu | 86 1.6 20.1 0.1 3.0 4.2 55 | cup=133 each=130
potato, irish potato, baby potato | 77 2.0 17.5 0.1 2.2 0.8 6 | cup=150 each=150
cassava, muhogo, manioc | 160 1.4 38.1 0.3 1.8 1.7 14 | cup=206 each=400
plantain, green banana, matoke, cooking banana | 122 1.3 31.9 0.4 2.3 15.0 4 | cup=148 each=179
banana, ripe banana | 89 1.1 22.8 0.3 2.6 12.2 1 | cup=225 each=118
avocado | 160 2.0 8.5 14.7 6.7 0.7 7 | cup=150 each=136
cucumber | 15 0.7 3.6 0.1 0.5 1.7 2 | cup=104 each=200
bell pepper, capsicum, green pepper, red pepper, yellow pepper, sweet pepper, pepper | 26 0.9 5.3 0.3 1.9 3.3 4 | cup=149 each=119
chili flake, chilli flake, crushed red pepper, red pepper flake | 318 12.0 56.6 17.3 27.2 10.3 30 | tsp=1.8
chili, chilli, chilly, chily, chili pepper, chile, scotch bonnet, jalapeno, jalape os, jalape o, birds eye chili | 40 2.0 9.5 0.2 1.5 5.1 7 | each=10 tsp=3 tbsp=9
green pea, pea, garden pea, petit pois | 81 5.4 14.5 0.4 5.1 5.7 5 | cup=145
sweet corn, sweetcorn, corn kernel, corn, maize kernel, maize | 86 3.3 19.0 1.4 2.0 6.3 15 | cup=154 each=90 cob=90
green bean, french bean, string bean | 31 1.8 7.0 0.2 2.7 3.3 6 | cup=110
mushroom | 22 3.1 3.3 0.3 1.0 2.0 5 | cup=70
eggplant, aubergine, brinjal | 25 1.0 5.9 0.2 3.0 3.5 2 | cup=82
butternut squash, butternut | 45 1.0 11.7 0.1 2.0 2.2 4 | cup=140
pumpkin | 26 1.0 6.5 0.1 0.5 2.8 1 | cup=116
zucchini, courgette | 17 1.2 3.1 0.3 1.0 2.5 8 | cup=113 each=196
broccoli | 34 2.8 6.6 0.4 2.6 1.7 33 | cup=91 head=300
cauliflower | 25 1.9 5.0 0.3 2.0 1.9 30 | cup=107 head=600
cabbage | 25 1.3 5.8 0.1 2.5 3.2 18 | cup=70 head=900 each=900
celery | 14 0.7 3.0 0.2 1.6 1.3 80 | cup=101 stalk=40
lettuce, romaine, salad leaf, mixed green, salad green | 17 1.2 3.3 0.3 2.1 1.2 8 | cup=47
spinach | 23 2.9 3.6 0.4 2.2 0.4 79 | cup=30
sukuma wiki, sukuma, kale, collard green, collard | 32 3.0 5.4 0.6 4.0 0.5 17 | cup=36 bunch=300
terere, amaranth, amaranth leaf, african spinach | 23 2.5 4.0 0.3 2.2 0.0 20 | cup=28 bunch=250

# ---- fruit -----------------------------------------------------------------
lemon juice | 22 0.4 6.9 0.2 0.3 2.5 1 | cup=244 each=48
lime juice | 25 0.4 8.4 0.1 0.4 1.7 2 | cup=242 each=30
lemon | 29 1.1 9.3 0.3 2.8 2.5 2 | each=58 slice=6
lime | 30 0.7 10.5 0.2 2.8 1.7 2 | each=67 slice=6
orange juice | 45 0.7 10.4 0.2 0.2 8.4 1 | cup=248
orange | 47 0.9 11.8 0.1 2.4 9.4 0 | each=131
mango | 60 0.8 15.0 0.4 1.6 13.7 1 | cup=165 each=207
pineapple | 50 0.5 13.1 0.1 1.4 9.9 1 | cup=165
passion fruit, passionfruit | 97 2.2 23.4 0.7 10.4 11.2 28 | each=18 cup=236
papaya, pawpaw | 43 0.5 10.8 0.3 1.7 7.8 8 | cup=140
apple | 52 0.3 13.8 0.2 2.4 10.4 1 | cup=125 each=182
blueberry | 57 0.7 14.5 0.3 2.4 10.0 1 | cup=148
strawberry | 32 0.7 7.7 0.3 2.0 4.9 1 | cup=152
date | 282 2.5 75.0 0.4 8.0 63.4 2 | each=8 cup=147
raisin, sultana | 299 3.1 79.2 0.5 3.7 59.2 11 | cup=145

lemon zest, lime zest, zest | 47 1.5 16.0 0.3 10.6 4.2 6 | tsp=2 tbsp=6
orange zest | 97 1.5 25.0 0.2 10.6 0.0 3 | tsp=2 tbsp=6
chive | 30 3.3 4.4 0.7 2.5 1.9 3 | cup=48

# ---- oils, sauces, stock ---------------------------------------------------
olive oil | 884 0.0 0.0 100.0 0.0 0.0 2 | cup=216
coconut oil | 862 0.0 0.0 100.0 0.0 0.0 0 | cup=218
oil, vegetable oil, cooking oil, sunflower oil, canola oil, corn oil, rapeseed oil | 884 0.0 0.0 100.0 0.0 0.0 0 | cup=218
soy sauce, soya sauce | 53 8.1 4.9 0.6 0.8 0.4 5493 | cup=255
vinegar, white vinegar, apple cider vinegar, cider vinegar | 18 0.0 0.0 0.0 0.0 0.0 2 | cup=239
ketchup, tomato ketchup, tomato sauce | 101 1.0 27.4 0.1 0.3 21.3 907 | cup=240
mayonnaise, mayo | 680 1.0 0.6 74.9 0.0 0.6 635 | cup=220
mustard, dijon mustard | 60 3.7 5.8 3.3 4.0 0.9 1135 | cup=250
stock, broth, vegetable broth, chicken broth, beef broth, vegetable stock, chicken stock, beef stock | 4 0.5 0.4 0.1 0.0 0.4 330 | cup=240
salt, table salt, sea salt, kosher salt | 0 0.0 0.0 0.0 0.0 0.0 38758 | tsp=6
tea leaf, black tea, tea, tea bag, chai | 0 0.0 0.0 0.0 0.0 0.0 0 | tsp=2 each=2
coffee, instant coffee | 0 0.0 0.0 0.0 0.0 0.0 0 | tsp=2

# ---- spices & herbs --------------------------------------------------------
black pepper, ground pepper | 251 10.4 63.9 3.3 25.3 0.6 20 | tsp=2.3
curry powder, curry | 325 14.3 55.8 14.0 53.2 2.8 52 | tsp=2 tbsp=6
paprika, smoked paprika | 282 14.1 54.0 12.9 34.9 10.3 68 | tsp=2.3
cumin, ground cumin, cumin seed, jeera | 375 17.8 44.2 22.3 10.5 2.3 168 | tsp=2.1
turmeric, tumeric, manjano | 312 9.7 67.1 3.3 22.7 3.2 27 | tsp=3
cinnamon | 247 4.0 80.6 1.2 53.1 2.2 10 | tsp=2.6 stick=2.5 each=2.5
cardamom, cardamon, iliki, hiliki | 311 10.8 68.5 6.7 28.0 0.0 18 | tsp=2 pod=0.3
nutmeg | 525 5.8 49.3 36.3 20.8 28.5 16 | tsp=2.2
clove, karafuu, ground clove | 274 6.0 65.5 13.0 33.9 2.4 277 | tsp=2.1
chili powder, chilli powder | 282 13.5 49.7 14.3 34.8 7.2 1640 | tsp=2.6
cayenne, cayenne pepper | 318 12.0 56.6 17.3 27.2 10.3 30 | tsp=1.8
coriander seed, ground coriander, coriander powder, coriander spice | 298 12.4 55.0 17.8 41.9 0.0 35 | tsp=1.8
garam masala, masala, pilau masala, mixed spice, spice | 325 14.3 55.8 14.0 40.0 2.8 52 | tsp=2
oregano | 265 9.0 68.9 4.3 42.5 4.1 25 | tsp=1
cilantro, fresh coriander, coriander leaf, dhania, dania, coriander | 23 2.1 3.7 0.5 2.8 0.9 46 | cup=16 bunch=40
parsley | 36 3.0 6.3 0.8 3.3 0.9 56 | cup=60 bunch=60
dill | 43 3.5 7.0 1.1 2.1 0.0 61 | cup=20
mint | 44 3.3 8.4 0.7 6.8 0.0 30 | cup=50
basil | 23 3.2 2.7 0.6 1.6 0.3 4 | cup=24
thyme | 101 5.6 24.5 1.7 14.0 0.0 9 | tsp=1 sprig=1 each=1
rosemary | 131 3.3 20.7 5.9 14.1 0.0 26 | tsp=1 sprig=1 each=1
bay leaf | 313 7.6 75.0 8.4 26.3 0.0 23 | each=0.6
"""

_MINOR_UNIT_G = {'sprig': 1.0, 'pod': 0.3, 'leaf': 0.5, 'pinch': 0.3, 'dash': 0.3, 'handful': 15.0}

# Words that, on their own, are just preparation notes split off by the comma
# separator ("1 red onion, diced" -> "diced") and carry no ingredient.
_DESCRIPTORS = {
    'minced', 'chopped', 'diced', 'sliced', 'grated', 'shredded', 'crushed', 'cubed', 'peeled', 'softened',
    'melted', 'finely', 'roughly', 'thinly', 'freshly', 'fresh', 'cooked', 'boiled', 'drained', 'rinsed',
    'optional', 'divided', 'halved', 'quartered', 'julienned', 'mashed', 'beaten', 'sifted', 'packed',
    'and', 'or', 'to', 'of', 'the', 'a', 'an', 'for', 'extra', 'large', 'small', 'medium', 'pureed',
    'cut', 'into', 'pieces', 'piece', 'strips', 'strip', 'wedges', 'florets', 'slices', 'cubes', 'rings',
    'deveined', 'boneless', 'skinless', 'whole', 'ripe', 'raw', 'dried', 'ground', 'plus', 'more', 'about',
    'thin', 'thick', 'fine', 'coarse', 'coarsely', 'lightly', 'toasted', 'roasted', 'seeded', 'pitted',
    'trimmed', 'washed', 'cleaned', 'soaked', 'frozen', 'canned', 'tinned', 'unsalted', 'salted',
}
_SKIP_NOTE = re.compile(r'\b(to taste|for garnish|garnish|for serving|to serve|optional|as needed|for decoration|'
                        r'for dusting|for sprinkling|for topping|see notes?|for dipping|for drizzling|for brushing)\b')
_FRYING_NOTE = re.compile(r'\b(for frying|for deep frying|for cooking|for greasing|for sauteing|for sautéing|'
                          r'for shallow frying|for pan frying|to cook|to fry)\b')
_SECTION_HEADER = re.compile(r'^(for|to)\s+(the\s+)?[a-z ]+:?$')
_COOKED_HINT = re.compile(r'\b(cooked|boiled|canned|tinned|drained|steamed|leftover)\b')

_UNIT_ALIASES = {
    'cup': 'cup', 'cups': 'cup', 'c': 'cup',
    'tbsp': 'tbsp', 'tbs': 'tbsp', 'tbsps': 'tbsp', 'tablespoon': 'tbsp', 'tablespoons': 'tbsp', 'tbl': 'tbsp',
    'tsp': 'tsp', 'tsps': 'tsp', 'teaspoon': 'tsp', 'teaspoons': 'tsp',
    'g': 'g', 'gm': 'g', 'gms': 'g', 'gram': 'g', 'grams': 'g', 'gramme': 'g',
    'kg': 'kg', 'kgs': 'kg', 'kilo': 'kg', 'kilos': 'kg', 'kilogram': 'kg', 'kilograms': 'kg',
    'oz': 'oz', 'ounce': 'oz', 'ounces': 'oz',
    'lb': 'lb', 'lbs': 'lb', 'pound': 'lb', 'pounds': 'lb',
    'ml': 'ml', 'millilitre': 'ml', 'milliliter': 'ml', 'millilitres': 'ml', 'milliliters': 'ml',
    'l': 'l', 'litre': 'l', 'liter': 'l', 'litres': 'l', 'liters': 'l',
    'clove': 'clove', 'cloves': 'clove',
    'can': 'can', 'cans': 'can', 'tin': 'can', 'tins': 'can',
    'slice': 'slice', 'slices': 'slice',
    'head': 'head', 'heads': 'head',
    'stick': 'stick', 'sticks': 'stick',
    'bunch': 'bunch', 'bunches': 'bunch',
    'sprig': 'sprig', 'sprigs': 'sprig',
    'pod': 'pod', 'pods': 'pod',
    'pinch': 'pinch', 'pinches': 'pinch', 'dash': 'dash', 'dashes': 'dash',
    'handful': 'handful', 'handfuls': 'handful',
    'leaf': 'leaf', 'leaves': 'leaf',
    'scoop': 'scoop', 'scoops': 'scoop',
    'stalk': 'stalk', 'stalks': 'stalk',
    'cob': 'cob', 'cobs': 'cob',
    'piece': 'each', 'pieces': 'each', 'whole': 'each', 'fillet': 'each', 'fillets': 'each',
    'breast': 'each', 'breasts': 'each', 'thigh': 'each', 'thighs': 'each', 'drumstick': 'each', 'drumsticks': 'each',
}
_FILLER = {'a', 'an', 'of', 'heaped', 'heaping', 'level', 'scant', 'generous', 'rounded', 'big', 'about', 'approx',
           'approximately', 'around', 'roughly'}
_SIZE_FACTOR = {'small': 0.75, 'medium': 1.0, 'large': 1.3, 'big': 1.3}
_UNICODE_FRAC = {'¼': ' 1/4', '½': ' 1/2', '¾': ' 3/4', '⅓': ' 1/3', '⅔': ' 2/3', '⅛': ' 1/8', '⅜': ' 3/8'}

_G_PER_OZ = 28.35
_G_PER_LB = 453.6
_ML_PER_CUP = 236.6

DAILY_VALUES = {  # FDA Daily Values, 2,000 kcal reference diet
    'kcal': 2000, 'protein': 50, 'carbs': 275, 'fat': 78, 'fiber': 28, 'sodium': 2300,
}


# --------------------------------------------------------------------------- #
# table loading
# --------------------------------------------------------------------------- #
_IRREGULAR_PLURALS = {'leaves': 'leaf', 'loaves': 'loaf', 'halves': 'half'}


def _singular(word):
    if word in _IRREGULAR_PLURALS:
        return _IRREGULAR_PLURALS[word]
    if len(word) > 4 and word.endswith('ies'):
        return word[:-3] + 'y'
    if len(word) > 4 and word.endswith(('oes', 'ches', 'shes', 'xes', 'sses')):
        return word[:-2]
    if len(word) > 3 and word.endswith('s') and not word.endswith(('ss', 'us', 'is')):
        return word[:-1]
    return word


def _tokens(text):
    text = text.lower().replace('\xa0', ' ')
    return [_singular(w) for w in re.findall(r"[a-z]+(?:-[a-z]+)*", text)]


def _parse_units(text):
    units = {}
    for part in text.split():
        if '=' in part:
            k, v = part.split('=', 1)
            units[k] = float(v)
    if 'cup' in units:
        units.setdefault('tbsp', units['cup'] / 16)
        units.setdefault('tsp', units['cup'] / 48)
    elif 'tsp' in units:
        units.setdefault('tbsp', units['tsp'] * 3)
        units.setdefault('cup', units['tsp'] * 48)
    return units


def _parse_row(line):
    parts = [p.strip() for p in line.split('|')]
    nums = [float(x) for x in parts[1].split()]
    keys = ('kcal', 'protein', 'carbs', 'fat', 'fiber', 'sugar', 'sodium')
    return dict(zip(keys, nums)), _parse_units(parts[2] if len(parts) > 2 else '')


def _load_table():
    entries = []
    for raw in _TABLE.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith('#'):
            continue
        if line.startswith('  cooked'):
            nutr, units = _parse_row(line)
            entries[-1]['cooked'] = {'n': nutr, 'u': {**entries[-1]['u'], **units}}
            continue
        names = [n.strip() for n in line.split('|')[0].split(',') if n.strip()]
        nutr, units = _parse_row(line)
        entries.append({'name': names[0], 'aliases': names, 'n': nutr, 'u': units})
    return entries


INGREDIENTS = _load_table()


def _build_index():
    index = []  # (alias token tuple, entry order, entry)
    for order, entry in enumerate(INGREDIENTS):
        for alias in entry['aliases']:
            toks = tuple(_tokens(alias))
            if toks:
                index.append((toks, order, entry))
    # longest alias first, then table order, so "coconut milk" beats "milk"
    index.sort(key=lambda x: (-len(x[0]), -sum(len(t) for t in x[0]), x[1]))
    return index


_INDEX = _build_index()


def find_ingredient(name):
    """Return the table entry whose alias appears (as whole words) in `name`."""
    toks = _tokens(name)
    if not toks:
        return None
    joined = ' ' + ' '.join(toks) + ' '
    for alias, _order, entry in _INDEX:
        if ' ' + ' '.join(alias) + ' ' in joined:
            return entry
    return None


# --------------------------------------------------------------------------- #
# ingredient line parsing
# --------------------------------------------------------------------------- #
def _num(text):
    text = text.strip()
    total = 0.0
    for piece in text.split():
        if '/' in piece:
            a, b = piece.split('/')
            total += float(a) / float(b)
        else:
            total += float(piece)
    return total


_NUM = r'(?:\d+/\d+|\d+(?:\.\d+)?(?:\s+\d+/\d+)?)'   # fraction first, so "1/2" is not read as "1"
_QTY_RE = re.compile(r'^\s*(' + _NUM + r')(?:\s*(?:-|–|to)\s*(' + _NUM + r'))?')


def _prep(text):
    text = text.replace('\xa0', ' ').replace('▢', ' ').replace('☐', ' ').replace('•', ' ')
    for ch, rep in _UNICODE_FRAC.items():
        text = re.sub(r'(\d)' + ch, r'\1' + rep, text)
        text = text.replace(ch, rep.strip() if text.strip().startswith(ch) else rep)
    text = re.sub(r'(\d)([a-zA-Z])', r'\1 \2', text)          # "3cloves" -> "3 cloves"
    text = re.sub(r'^(\d[\d/. ]* (?:cloves|clove|cups|cup|tablespoons|tablespoon|teaspoons|teaspoon|large|medium|small))(?=[a-z])', r'\1 ', text, flags=re.I)  # "3 clovesgarlic"
    text = re.sub(r'^(\d[\d/. ]*[a-zA-Z]+)\s*\(\s*\d[^)]*\)', r'\1', text)  # "1/2 cup(113.5g) butter" -> "1/2 cup butter"
    return re.sub(r'\s+', ' ', text).strip()


def split_ingredients(raw):
    """Split on commas that are not inside brackets; also on checkbox glyphs."""
    raw = raw.replace('▢', ',').replace('☐', ',')
    return [p.strip() for p in re.split(r',\s*(?![^()]*\))', raw) if p.strip()]


def _read_quantity(text):
    """-> (qty or None, unit or None, size_factor, remaining name text)"""
    text = _prep(text).lower()
    qty = None
    m = _QTY_RE.match(text)
    if m:
        lo = _num(m.group(1))
        hi = _num(m.group(2)) if m.group(2) else None
        qty = (lo + hi) / 2 if hi else lo
        text = text[m.end():].strip()
    elif re.match(r'^(a|an|one)\b', text):
        qty = 1.0
        text = re.sub(r'^(a|an|one)\b', '', text).strip()

    size = 1.0
    unit = None
    words = text.split()
    i = 0
    while i < len(words):
        w = words[i].strip('.,;:')
        if w in _FILLER:
            i += 1
            continue
        if w in _SIZE_FACTOR:
            size = _SIZE_FACTOR[w]
            i += 1
            continue
        if w in _UNIT_ALIASES:
            unit = _UNIT_ALIASES[w]
            i += 1
            # skip a trailing "of"
            if i < len(words) and words[i] == 'of':
                i += 1
        break
    return qty, unit, size, ' '.join(words[i:])


def _to_grams(entry, qty, unit, size, cooked):
    units = entry['cooked']['u'] if cooked and 'cooked' in entry else entry['u']
    g = None
    if unit == 'g':
        g = qty
    elif unit == 'kg':
        g = qty * 1000
    elif unit == 'oz':
        g = qty * _G_PER_OZ
    elif unit == 'lb':
        g = qty * _G_PER_LB
    elif unit in ('ml', 'l'):
        ml = qty * (1000 if unit == 'l' else 1)
        density = units['cup'] / _ML_PER_CUP if 'cup' in units else 1.0
        g = ml * density
    elif unit in ('cup', 'tbsp', 'tsp'):
        if unit in units:
            g = qty * units[unit]
    elif unit is None or unit == 'each':
        if 'each' in units:
            g = qty * units['each'] * size
    elif unit in units:
        g = qty * units[unit]
    elif unit == 'clove' and 'each' in units:
        g = qty * units['each']
    elif unit in _MINOR_UNIT_G:
        g = qty * _MINOR_UNIT_G[unit]
    return g


def parse_ingredient(item):
    """
    Parse one ingredient line.

    Returns a dict: {'text', 'status', 'grams', 'entry'} where status is one of
    'counted'   - matched and converted to grams
    'skipped'   - not an ingredient to count (section header, "to taste", prep note)
    'frying'    - cooking oil with no quantity
    'unmatched' - could not match the name or convert the quantity
    """
    original = item.strip()
    low = _prep(original).lower()

    if not re.search(r'[a-z]', low):
        return {'text': original, 'status': 'skipped'}
    if _FRYING_NOTE.search(low):
        return {'text': original, 'status': 'frying'}
    if _SKIP_NOTE.search(low):
        return {'text': original, 'status': 'skipped'}
    if low.endswith(':') or (_SECTION_HEADER.match(low) and not re.search(r'\d', low)):
        return {'text': original, 'status': 'skipped'}
    words = set(re.findall(r'[a-z]+', low))
    if words and words <= _DESCRIPTORS:
        return {'text': original, 'status': 'skipped'}
    if words <= {'water', 'warm', 'hot', 'cold', 'boiling', 'lukewarm', 'ice', 'cube', 'cubes', 'tap', 'cool'}:
        return {'text': original, 'status': 'skipped'}

    # "juice of 2 lemons" -> 2 x lemon juice
    jm = re.match(r'^(?:the )?juice of (?:(\d+(?:\.\d+)?|a|an|one|half(?: a)?)\s+)?(lemon|lime|orange)s?\b', low)
    if jm:
        word = jm.group(1) or '1'
        amount = 0.5 if word.startswith('half') else (1.0 if word in ('a', 'an', 'one') else float(word))
        entry = find_ingredient(jm.group(2) + ' juice')
        grams = _to_grams(entry, amount, None, 1.0, False) if entry else None
        if grams:
            return {'text': original, 'status': 'counted', 'grams': grams, 'entry': entry, 'cooked': False}
        return {'text': original, 'status': 'unmatched', 'reason': 'name'}

    # Format A: "Name (1 1/2 cups, chopped)"; Format B: "1 1/2 cups of chopped name"
    qty = unit = None
    size = 1.0
    name = low
    paren = re.search(r'\(([^()]*)\)\s*$', low)
    if paren and not re.match(r'^\s*\d', low):
        inner = paren.group(1)
        name = low[:paren.start()].strip()
        if _FRYING_NOTE.search(inner):
            return {'text': original, 'status': 'frying'}
        if _SKIP_NOTE.search(inner):
            return {'text': original, 'status': 'skipped'}
        qty, unit, size, _rest = _read_quantity(inner)
        if qty is None and unit in ('pinch', 'dash'):
            qty = 1.0
    else:
        qty, unit, size, name = _read_quantity(low)
        if qty is None and unit in ('pinch', 'dash', 'handful'):
            qty = 1.0

    name_tokens = _tokens(name)
    # "pasta water", "rice water": cooking liquid, not the ingredient itself
    if name_tokens and name_tokens[-1] == 'water' and 'coconut' not in name_tokens:
        return {'text': original, 'status': 'skipped'}
    # bare "salt", "pepper", "salt and pepper" with no amount: seasoning to taste
    if qty is None and re.match(r'^(salt|pepper|black pepper|ground pepper|salt (and|&) (black |ground )?pepper)\b', name):
        return {'text': original, 'status': 'skipped'}

    entry = find_ingredient(name)
    if entry is None:
        hint = None
        if qty is not None and unit in ('g', 'kg', 'oz', 'lb'):
            hint = qty * {'g': 1, 'kg': 1000, 'oz': _G_PER_OZ, 'lb': _G_PER_LB}[unit]
        return {'text': original, 'status': 'unmatched', 'reason': 'name', 'hint_g': hint}
    if qty is None:
        return {'text': original, 'status': 'unmatched', 'reason': 'quantity', 'entry': entry}

    cooked = bool(_COOKED_HINT.search(low))
    grams = _to_grams(entry, qty, unit, size, cooked)
    if grams is None or grams <= 0 or grams > 6000:
        return {'text': original, 'status': 'unmatched', 'reason': 'unit', 'entry': entry}
    return {'text': original, 'status': 'counted', 'grams': grams, 'entry': entry, 'cooked': cooked}


# --------------------------------------------------------------------------- #
# recipe-level estimate
# --------------------------------------------------------------------------- #
MIN_COVERAGE = 0.6          # below this we do not show numbers at all
GOOD_COVERAGE = 0.85
MAX_PLAUSIBLE_KCAL_PER_SERVING = 1600
MIN_PLAUSIBLE_KCAL_PER_SERVING = 15
# A real dish (not a drink, tea, condiment or garnish-style item) under this is almost
# certainly missing its main ingredient, so we show nothing rather than a wrong number.
MIN_KCAL_FOR_A_DISH = 60
LOW_CALORIE_CATEGORIES = {'Beverage', 'Condiment', 'Salad'}


def estimate_nutrition(ingredients_raw, servings, category=None):
    """
    Estimate per-serving nutrition for a recipe.

    Returns None when too little of the ingredient list could be counted for
    the numbers to mean anything, otherwise a dict of per-serving values plus
    the whole-recipe total, a coverage ratio and the ingredients left out.
    """
    items = [parse_ingredient(p) for p in split_ingredients(ingredients_raw)]
    counted = [i for i in items if i['status'] == 'counted']
    unmatched = [i for i in items if i['status'] == 'unmatched']
    considered = len(counted) + len(unmatched)
    if not considered or not counted:
        return None
    coverage = len(counted) / considered
    if coverage < MIN_COVERAGE:
        return None
    # An unrecognised ingredient that is clearly a big part of the dish (>= 150 g) would
    # make the totals badly wrong, so show nothing instead.
    if any((u.get('hint_g') or 0) >= 150 for u in unmatched):
        return None

    total = dict.fromkeys(('kcal', 'protein', 'carbs', 'fat', 'fiber', 'sugar', 'sodium'), 0.0)
    for it in counted:
        entry = it['entry']
        values = entry['cooked']['n'] if it['cooked'] and 'cooked' in entry else entry['n']
        factor = it['grams'] / 100.0
        for k in total:
            total[k] += values[k] * factor

    servings = max(1, int(servings or 1))
    per = {k: v / servings for k, v in total.items()}
    floor = MIN_PLAUSIBLE_KCAL_PER_SERVING if category in LOW_CALORIE_CATEGORIES else MIN_KCAL_FOR_A_DISH
    if not (floor <= per['kcal'] <= MAX_PLAUSIBLE_KCAL_PER_SERVING):
        return None

    notes = []
    if any(i['status'] == 'frying' for i in items):
        notes.append('Oil used for frying is not counted.')
    if any(i['status'] == 'skipped' and _SKIP_NOTE.search(i['text'].lower()) and 'salt' in i['text'].lower()
           for i in items):
        notes.append('Salt added "to taste" is not counted, so sodium may be higher.')

    def r(v, nd=0):
        return round(v, nd) if nd else int(round(v))

    return {
        'servings': servings,
        'per_serving': {
            'kcal': r(per['kcal']), 'protein': r(per['protein'], 1), 'carbs': r(per['carbs'], 1),
            'fat': r(per['fat'], 1), 'fiber': r(per['fiber'], 1), 'sugar': r(per['sugar'], 1),
            'sodium': r(per['sodium']),
        },
        'total': {
            'kcal': r(total['kcal']), 'protein': r(total['protein'], 1), 'carbs': r(total['carbs'], 1),
            'fat': r(total['fat'], 1), 'fiber': r(total['fiber'], 1), 'sugar': r(total['sugar'], 1),
            'sodium': r(total['sodium']),
        },
        'coverage': round(coverage, 2),
        'confidence': 'good' if coverage >= GOOD_COVERAGE else 'fair',
        'left_out': [u['text'].strip() for u in unmatched][:6],
        'notes': notes,
    }
