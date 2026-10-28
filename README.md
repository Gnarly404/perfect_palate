# Perfect Palate - Personalized Recipe & Meal Recommendation System

A Flask-based web application for Kenyan cuisine recipe recommendations with meal planning, favorites, and shopping list features.

## Setup Instructions

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Environment Setup
Create a `.env` file in the root directory with:
```
SECRET_KEY=your-secret-key-here
FLASK_ENV=development
PUBLIC_BASE_URL=http://localhost:5000
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your-smtp-username
SMTP_PASSWORD=your-smtp-password
SMTP_FROM_EMAIL=no-reply@example.com
SMTP_FROM_NAME=Perfect Palate
SMTP_USE_TLS=true
SMTP_USE_SSL=false
```

Password reset emails are sent through the configured SMTP server using STARTTLS by default. Configure these variables in the deployment environment (not in source control) with credentials and a sender address authorized by your email provider. Set `PUBLIC_BASE_URL` to the public HTTPS origin of the deployed app so reset links point to the correct site. For implicit TLS providers, use port `465`, set `SMTP_USE_SSL=true`, and set `SMTP_USE_TLS=false`. If the provider does not require authentication, leave both `SMTP_USERNAME` and `SMTP_PASSWORD` empty. Reset requests return an error if SMTP is missing or delivery fails; failed deliveries do not leave a usable reset token.

### 3. Initialize Database
```bash
python -c "from database import init_db; init_db()"
```

### 4. Run the Application
```bash
python app.py
```

The application will be available at `http://localhost:5000`

## Project Structure

- **app.py** - Main Flask application with routes
- **database.py** - SQLite database initialization and connection helpers
- **recommendations.py** - Recipe recommendations, search, and filtering blueprint
- **meal_planner.py** - Meal planning and favorites blueprint
- **nutrition.py** - Per-serving nutrition estimates from ingredient lists
- **difficulty.py** - Easy / Medium / Hard rating derived from steps, ingredients and techniques
- **tips.py** - Cooking tips, techniques and food-safety advice, matched to recipes
- **test_enhancements.py** - Tests for the features above
- **templates/** - Jinja2 HTML templates
- **static/** - CSS, JavaScript, and image assets
- **Dataset/** - Recipe CSV data and recipe images
- **instance/** - SQLite database (auto-created)

## Features

- User authentication (email/password)
- Health condition, allergy, and dietary preference tracking
- Recipe recommendations with personalized filtering
- 7-day meal planner
- Recipe favorites management
- Automated shopping list generation
- Cook Mode for hands-free recipe viewing
- **Profile customisation** (`/profile`): display name, bio, avatar and colour, cooking level, optional daily calorie goal, password change
- **Nutritional information**: estimated calories, protein, carbs, sugars, fat, fibre and sodium per serving, with % daily value
- **Recipe difficulty levels**: Easy / Medium / Hard badges, a difficulty filter and a "For your level" filter
- **Cooking tips and techniques**: recipe-specific tips (food safety first) on each recipe and in Cook Mode, plus a library at `/recipes/tips`
- **Social sharing**: shareable recipe links (`/recipes/recipe/<id>`) with link-preview tags, WhatsApp, X, Facebook, copy link and the device share sheet

## How the new data is produced

The recipe dataset has no nutrition, difficulty or servings columns, so these are **derived**, and labelled that way in the app:

- **Nutrition** is estimated by parsing each ingredient line, converting it to grams and multiplying by per-100 g reference values (USDA FoodData Central style, typed into `nutrition.py`). Servings come from a category default, not the source recipe. When too little of the ingredient list can be matched (under 60%), or a large ingredient is unrecognised, no estimate is shown. Oil "for frying" and salt "to taste" are not counted. It is general information, not medical advice.
- **Difficulty** is the sum of a step-count band, an ingredient-count band and the number of technique keywords (kneading, deep frying, folding, ...). Each recipe lists the reasons.
- **Duplicate recipe IDs**: the CSV reuses 34 IDs. The first recipe keeps its ID; later ones are given new IDs above the file's maximum, so favourites saved against a reused ID now point at the first recipe only.
- Existing databases are upgraded in place on startup (new profile columns on `users`).

## Bug Fix Log

- [ ] Implement password hashing with bcrypt
- [ ] Add session validation middleware
- [ ] Implement shopping list categorization
- [ ] Add recipe rating/review system
- [ ] Implement meal plan persistence

## Future Enhancements

- Servings scaling and a nutrition column in the dataset
- Per-user ratings and reviews
- Profile photo uploads
