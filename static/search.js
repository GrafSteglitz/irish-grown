export function initSearch(inputId, resultsId) {
    const searchInput = document.getElementById(inputId);
    if (!searchInput) return;

    // Ensure results container exists
    let resultsContainer = document.getElementById(resultsId);
    if (!resultsContainer) {
        resultsContainer = document.createElement('div');
        resultsContainer.id = resultsId;
        resultsContainer.className = 'search-results';
        searchInput.parentNode.appendChild(resultsContainer);
    }

    let timeout = null;

    function scrollResultsIntoView(container) {
        // Wait one frame for the dropdown to be painted and sized
        requestAnimationFrame(() => {
            const rect = container.getBoundingClientRect();
            const viewportBottom = window.innerHeight;
            if (rect.bottom > viewportBottom) {
                container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
        });
    }

    searchInput.addEventListener('input', (e) => {
        const query = e.target.value.trim();
        clearTimeout(timeout);

        if (query.length < 2) {
            resultsContainer.style.display = 'none';
            return;
        }

        timeout = setTimeout(async () => {
            try {
                const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
                const results = await response.json();

                if (results.length > 0) {
                    resultsContainer.innerHTML = results.map(p => `
                        <div class="search-result-item" data-id="${p.id}" data-producer="${p.producer || ''}" style="cursor:pointer">
                            <img src="${p.image && !p.image.startsWith('http') ? '/static/' + p.image : (p.image || '')}" alt="${p.name}" onerror="this.style.display='none'">
                            <div class="details">
                                <span class="name">${p.name}</span>
                                <span class="description">${p.producer ? '· ' + p.producer : ''}${p.description ? ' — ' + p.description : ''}</span>
                            </div>
                        </div>
                    `).join('');
                    resultsContainer.style.display = 'block';
                    scrollResultsIntoView(resultsContainer);
                } else {
                    resultsContainer.innerHTML = '<div class="search-result-item">No products found</div>';
                    resultsContainer.style.display = 'block';
                    scrollResultsIntoView(resultsContainer);
                }
            } catch (error) {
                console.error('Search error:', error);
            }
        }, 300);
    });

    // Close results when clicking outside
    document.addEventListener('click', (e) => {
        if (!searchInput.contains(e.target) && !resultsContainer.contains(e.target)) {
            resultsContainer.style.display = 'none';
        }
    });

    // Navigate to producer page when a result is clicked
    resultsContainer.addEventListener('click', (e) => {
        const item = e.target.closest('.search-result-item');
        if (item) {
            const producer = item.dataset.producer;
            resultsContainer.style.display = 'none';
            if (producer) {
                window.location.href = '/producers/' + encodeURIComponent(producer);
            } else {
                window.location.href = '/producers';
            }
        }
    });
}
