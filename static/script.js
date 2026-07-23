const API_URL = 'https://revers-ahuj.onrender.com';

const form = document.getElementById('downloadForm');
const urlInput = document.getElementById('urlInput');
const pasteBtn = document.getElementById('pasteBtn');
const goBtn = document.getElementById('goBtn');
const statusLine = document.getElementById('statusLine');
const deck = document.querySelector('.deck');
const shelfList = document.getElementById('shelfList');
const shelfCount = document.getElementById('shelfCount');

// єдиний аудіо-елемент на всю сторінку — грає завжди тільки один трек
const player = new Audio();
let playingUrl = null;

function setStatus(text, kind) {
    statusLine.textContent = text;
    statusLine.classList.remove('ok', 'err');
    if (kind) statusLine.classList.add(kind);
}

pasteBtn.addEventListener('click', async () => {
    try {
        const text = (await navigator.clipboard.readText()).trim();
        if (!text) {
            setStatus('Буфер обміну порожній.', 'err');
            return;
        }
        if (!/^https?:\/\//i.test(text)) {
            setStatus('У буфері немає посилання.', 'err');
            return;
        }
        urlInput.value = text;
        setStatus('Посилання вставлено. Можна записувати.', 'ok');
    } catch (err) {
        setStatus('Не вдалось прочитати буфер обміну.', 'err');
    }
});

form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const url = urlInput.value.trim();

    if (!url) {
        setStatus('Спочатку встав посилання.', 'err');
        return;
    }

    goBtn.disabled = true;
    deck.classList.add('is-recording');
    setStatus('Дека крутиться, витягуємо звук...');

    try {
        const res = await fetch(`${API_URL}/api/download`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ url })
        });

        const data = await res.json();

        if (!res.ok || !data.ok) {
            setStatus(data.error || 'Не вдалося завантажити доріжку.', 'err');
            return;
        }

        setStatus(`Готово: ${data.artist} — ${data.title}`, 'ok');
        urlInput.value = '';
        await loadShelf();
    } catch (err) {
        setStatus('Сервер не відповідає. Спробуй ще раз.', 'err');
    } finally {
        goBtn.disabled = false;
        deck.classList.remove('is-recording');
    }
});

async function loadShelf() {
    try {
        const res = await fetch(`${API_URL}/api/library`, {
            credentials: 'include'
        });
        const data = await res.json();
        const files = data.files || [];

        shelfCount.textContent = `${files.length} ${pluralTracks(files.length)}`;

        if (files.length === 0) {
            shelfList.innerHTML = '<li class="shelf__empty">Тут з\'являться завантажені треки.</li>';
            return;
        }

        shelfList.innerHTML = files.map((f) => {
            const fileUrl = f.url.startsWith('http') ? f.url : `${API_URL}${f.url}`;
            return `
              <li class="shelf__item" data-url="${fileUrl}">
                <button class="shelf__play" aria-label="Слухати">
                  <span class="shelf__playIcon">▶</span>
                </button>
                <div class="shelf__meta">
                  <span class="shelf__title">${escapeHtml(f.title)}</span>
                  <span class="shelf__artist">${escapeHtml(f.artist)}</span>
                  <div class="shelf__progress"><div class="shelf__progressBar"></div></div>
                </div>
                <a class="shelf__dl" href="${fileUrl}" download title="Завантажити файл">⬇</a>
              </li>
            `;
        }).join('');

        shelfList.querySelectorAll('.shelf__play').forEach(btn => {
            btn.addEventListener('click', () => togglePlay(btn));
        });
    } catch (err) {
        // мовчки лишаємо попередній стан полиці
    }
}

function togglePlay(btn) {
    const item = btn.closest('.shelf__item');
    const url = item.dataset.url;
    const icon = btn.querySelector('.shelf__playIcon');

    if (playingUrl === url && !player.paused) {
        player.pause();
        icon.textContent = '▶';
        return;
    }

    if (playingUrl !== url) {
        player.src = url;
        playingUrl = url;
    }

    player.play();
    refreshAllIcons();
}

function refreshAllIcons() {
    document.querySelectorAll('.shelf__item').forEach(item => {
        const isCurrent = item.dataset.url === playingUrl;
        const icon = item.querySelector('.shelf__playIcon');
        const bar = item.querySelector('.shelf__progressBar');
        item.classList.toggle('is-playing', isCurrent && !player.paused);
        if (icon) icon.textContent = (isCurrent && !player.paused) ? '⏸' : '▶';
        if (!isCurrent && bar) bar.style.width = '0%';
    });
}

player.addEventListener('play', refreshAllIcons);
player.addEventListener('pause', refreshAllIcons);
player.addEventListener('ended', () => {
    playingUrl = null;
    refreshAllIcons();
});
player.addEventListener('timeupdate', () => {
    if (!player.duration) return;
    const pct = (player.currentTime / player.duration) * 100;
    document.querySelectorAll('.shelf__item').forEach(item => {
        if (item.dataset.url === playingUrl) {
            const bar = item.querySelector('.shelf__progressBar');
            if (bar) bar.style.width = `${pct}%`;
        }
    });
});

function pluralTracks(n) {
    const mod10 = n % 10;
    const mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return 'доріжка';
    if ([2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100)) return 'доріжки';
    return 'доріжок';
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

loadShelf();
