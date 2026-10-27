// Perfect Palate - Main JavaScript

// Navbar Toggle
document.addEventListener('DOMContentLoaded', function() {
    const navbarToggle = document.getElementById('navbarToggle');
    const navbarMenu = document.getElementById('navbarMenu');

    if (navbarToggle) {
        navbarToggle.addEventListener('click', function() {
            navbarMenu.classList.toggle('active');
        });
    }

    // Close menu when clicking on a link
    const navLinks = document.querySelectorAll('.nav-link');
    navLinks.forEach(link => {
        link.addEventListener('click', function() {
            navbarMenu.classList.remove('active');
        });
    });
});

// Recipe Search
const recipeSearch = document.getElementById('recipeSearch');
if (recipeSearch) {
    recipeSearch.addEventListener('input', function(e) {
        const query = e.target.value;
        if (query.length > 0) {
            fetch(`/recipes/search?q=${query}`)
                .then(response => response.json())
                .then(data => {
                    console.log('Search results:', data);
                    // Update UI with search results
                });
        }
    });
}

// Add to Favorites
function addToFavorites(recipeId) {
    fetch(`/planner/favorite/${recipeId}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'added') {
            alert('Recipe added to favorites!');
        }
    })
    .catch(error => console.error('Error:', error));
}

// Remove from Favorites
function removeFavorite(recipeId) {
    if (confirm('Remove this recipe from favorites?')) {
        fetch(`/planner/favorite/${recipeId}`, {
            method: 'DELETE'
        })
        .then(response => response.json())
        .then(data => {
            location.reload();
        })
        .catch(error => console.error('Error:', error));
    }
}

// Shopping List Checkbox
const listItems = document.querySelectorAll('.list-item input[type="checkbox"]');
listItems.forEach(item => {
    item.addEventListener('change', function() {
        const label = this.nextElementSibling;
        if (this.checked) {
            label.style.textDecoration = 'line-through';
            label.style.opacity = '0.6';
        } else {
            label.style.textDecoration = 'none';
            label.style.opacity = '1';
        }
    });
});

// Utility Functions
function formatDate(date) {
    return new Date(date).toLocaleDateString();
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    document.body.appendChild(notification);

    setTimeout(() => {
        notification.remove();
    }, 3000);
}

// Export for shopping list
function exportShoppingList() {
    const listItems = Array.from(document.querySelectorAll('.list-item label'))
        .map(label => label.textContent)
        .join('\n');

    const element = document.createElement('a');
    element.setAttribute('href', 'data:text/plain;charset=utf-8,' + encodeURIComponent(listItems));
    element.setAttribute('download', 'shopping-list.txt');
    element.style.display = 'none';
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
}
