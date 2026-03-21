const CONFIG = {
    // A secret key to authorize requests to your backend. 
    // This MUST match the MOVIEHUB_API_KEY environment variable in Vercel.
    API_KEY: "greenmovies",
    BACKEND_URL: "",
    IMDB_API: "https://api.imdbapi.dev/search?query="
};

const searchInput = document.getElementById('searchInput');
const searchButton = document.getElementById('searchButton');
const resultsTable = document.getElementById('resultsTable');
const resultsBody = document.getElementById('resultsBody');
const resultsContainerDiv = document.getElementById('results-container');
const loadingDiv = document.getElementById('loading');
const noResultsDiv = document.getElementById('no-results');

searchButton.addEventListener('click', performSearch);
searchInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') performSearch();
});

async function performSearch() {
    const query = searchInput.value.trim();
    if (!query) return;

    // Reset UI
    resultsContainerDiv.classList.add('hidden');
    noResultsDiv.classList.add('hidden');
    loadingDiv.classList.remove('hidden');
    resultsBody.innerHTML = '';

    try {
        const response = await fetch(`${CONFIG.BACKEND_URL}/search?q=${encodeURIComponent(query)}&key=${CONFIG.API_KEY}`);
        const movies = await response.json();

        loadingDiv.classList.add('hidden');

        if (movies.length === 0) {
            noResultsDiv.classList.remove('hidden');
            return;
        }

        for (const movie of movies) {
            const row = await createMovieRow(movie);
            resultsBody.appendChild(row);
        }

        resultsContainerDiv.classList.remove('hidden');

    } catch (error) {
        console.error('Search error:', error);
        loadingDiv.classList.add('hidden');
        alert('An error occurred while searching. Please try again.');
    }
}

async function createMovieRow(movie) {
    const tr = document.createElement('tr');

    // Fetch poster
    let posterUrl = 'https://via.placeholder.com/100x150?text=No+Poster';
    try {
        const imdbResponse = await fetch(`${CONFIG.IMDB_API}${encodeURIComponent(movie.title)}`);
        const imdbData = await imdbResponse.json();
        if (imdbData.results && imdbData.results.length > 0 && imdbData.results[0].poster) {
            posterUrl = imdbData.results[0].poster;
        }
    } catch (e) {
        console.warn('IMDb API error for', movie.title, e);
    }

    // Prepare dropdown
    let optionsHtml = '';
    movie.files.forEach(file => {
        const selected = file.default ? 'selected' : '';
        optionsHtml += `<option value="${file.quality}" ${selected}>${file.quality} (${file.size})</option>`;
    });

    tr.innerHTML = `
        <td>
            <img src="${posterUrl}" alt="${movie.title}" class="poster-img" onerror="this.src='https://via.placeholder.com/100x150?text=Error'">
        </td>
        <td>
            <div class="movie-title">${movie.title}</div>
            <div class="movie-year">${movie.year}</div>
        </td>
        <td>
            <div class="download-section">
                <select id="quality-${movie._id}">
                    ${optionsHtml}
                </select>
                <button class="btn-download" onclick="downloadMovie('${movie._id}')">
                    <i class="fas fa-download"></i> Download
                </button>
            </div>
        </td>
    `;

    return tr;
}

function downloadMovie(movieId) {
    const quality = document.getElementById(`quality-${movieId}`).value;
    const downloadUrl = `${CONFIG.BACKEND_URL}/download/${movieId}/${quality}?key=${CONFIG.API_KEY}`;

    // Create a temporary link and trigger download
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}
