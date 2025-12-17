/**
 * Arena Battle JS
 * Handles zoom, drag, winner selection, and matchup loading
 */

// State
let battleCount = 0;
let isProcessing = false;
let lastBattle = null;  // For undo functionality

// Recent images history - prevent showing same images repeatedly
const RECENT_HISTORY_SIZE = 50;
let recentImages = [];  // Array of paths, most recent first

// Image transform state (per side)
const transforms = {
    left: { scale: 1, x: 0, y: 0 },
    right: { scale: 1, x: 0, y: 0 }
};

// Current image data
let currentImages = {
    left: null,
    right: null
};

/**
 * Add images to recent history (prevents showing same images repeatedly)
 */
function addToRecentHistory(path1, path2) {
    // Add both paths if not already in recent history
    if (path1 && !recentImages.includes(path1)) {
        recentImages.unshift(path1);
    }
    if (path2 && !recentImages.includes(path2)) {
        recentImages.unshift(path2);
    }
    // Trim to max size
    if (recentImages.length > RECENT_HISTORY_SIZE) {
        recentImages = recentImages.slice(0, RECENT_HISTORY_SIZE);
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    // Store initial image paths
    const imgLeft = document.getElementById('img-left');
    const imgRight = document.getElementById('img-right');

    currentImages.left = {
        path: imgLeft.dataset.path,
        element: imgLeft
    };
    currentImages.right = {
        path: imgRight.dataset.path,
        element: imgRight
    };

    // Track initial images in recent history
    addToRecentHistory(currentImages.left.path, currentImages.right.path);

    // Setup zoom and drag for both panels
    setupZoomDrag('left');
    setupZoomDrag('right');

    // Keyboard shortcuts
    document.addEventListener('keydown', handleKeyboard);

    // Stats are loaded with the initial page - no separate API call needed
});

/**
 * Setup zoom and drag functionality for a panel
 */
function setupZoomDrag(side) {
    const wrapper = document.getElementById(`wrapper-${side}`);
    const img = document.getElementById(`img-${side}`);

    let isDragging = false;
    let startX, startY;
    let startTransformX, startTransformY;

    // Prevent right-click context menu on wrapper
    wrapper.addEventListener('contextmenu', (e) => {
        e.preventDefault();
    });

    // Mouse wheel zoom
    wrapper.addEventListener('wheel', (e) => {
        e.preventDefault();

        const delta = e.deltaY > 0 ? 0.9 : 1.1;
        const transform = transforms[side];

        // Calculate zoom around cursor position
        const rect = wrapper.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        const centerX = rect.width / 2;
        const centerY = rect.height / 2;

        // Adjust position to zoom around cursor
        const newScale = Math.min(Math.max(transform.scale * delta, 0.5), 10);
        const scaleChange = newScale / transform.scale;

        transform.x = mouseX - (mouseX - centerX - transform.x) * scaleChange - centerX;
        transform.y = mouseY - (mouseY - centerY - transform.y) * scaleChange - centerY;
        transform.scale = newScale;

        applyTransform(side);
    }, { passive: false });

    // Right-click drag for panning
    wrapper.addEventListener('mousedown', (e) => {
        // Only start drag with RIGHT button (button === 2)
        if (e.button !== 2) return;
        if (transforms[side].scale <= 1) return;

        isDragging = true;
        startX = e.clientX;
        startY = e.clientY;
        startTransformX = transforms[side].x;
        startTransformY = transforms[side].y;
        wrapper.style.cursor = 'grabbing';
        e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;

        const dx = e.clientX - startX;
        const dy = e.clientY - startY;

        transforms[side].x = startTransformX + dx;
        transforms[side].y = startTransformY + dy;

        applyTransform(side);
    });

    document.addEventListener('mouseup', (e) => {
        if (isDragging && e.button === 2) {
            isDragging = false;
            wrapper.style.cursor = 'pointer';
        }
    });

    // Left-click selects winner
    wrapper.addEventListener('click', (e) => {
        if (e.button !== 0) return;  // Only left click
        selectWinner(side);
    });
}

/**
 * Apply transform to image
 */
function applyTransform(side) {
    const img = document.getElementById(`img-${side}`);
    const transform = transforms[side];
    img.style.transform = `translate(${transform.x}px, ${transform.y}px) scale(${transform.scale})`;
}

/**
 * Reset view for a side
 */
function resetView(side) {
    transforms[side] = { scale: 1, x: 0, y: 0 };
    applyTransform(side);
}

/**
 * Handle keyboard shortcuts
 */
function handleKeyboard(e) {
    if (isProcessing) return;

    // Ctrl+Z for undo
    if (e.ctrlKey && e.key === 'z') {
        e.preventDefault();
        undoLastBattle();
        return;
    }

    if (e.key === 'ArrowLeft') {
        selectWinner('left');
    } else if (e.key === 'ArrowRight') {
        selectWinner('right');
    }
}

/**
 * Select winner and log result
 */
async function selectWinner(side) {
    if (isProcessing) return;
    isProcessing = true;

    const winnerSide = side;
    const loserSide = side === 'left' ? 'right' : 'left';

    // Visual feedback
    const winnerWrapper = document.getElementById(`wrapper-${winnerSide}`);
    winnerWrapper.classList.add('winner-flash');
    setTimeout(() => winnerWrapper.classList.remove('winner-flash'), 300);

    // Store current matchup for undo
    lastBattle = {
        img1: { ...getCurrentImageData('left') },
        img2: { ...getCurrentImageData('right') }
    };

    // Prepare result data - include recent images to exclude
    const result = {
        winner_path: currentImages[winnerSide].path,
        loser_path: currentImages[loserSide].path,
        exclude_recent: recentImages,
        ...scopeData
    };

    try {
        // Send result to server
        const response = await fetch('/api/result', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(result)
        });

        if (!response.ok) {
            throw new Error('Failed to log result');
        }

        const data = await response.json();
        battleCount++;
        document.getElementById('battle-count').textContent = battleCount;

        // Store battle_id for potential undo
        lastBattle.battle_id = data.battle_id;

        // Load next matchup
        if (data.next) {
            // Track new images in recent history
            addToRecentHistory(data.next.img1.path, data.next.img2.path);
            loadMatchup(data.next);
        } else {
            alert('No more matchups available!');
        }

    } catch (error) {
        console.error('Error logging result:', error);
        alert('Error: ' + error.message);
        lastBattle = null;  // Clear on error
    }

    isProcessing = false;
}

/**
 * Get current image data for a side (for undo)
 */
function getCurrentImageData(side) {
    const img = document.getElementById(`img-${side}`);
    const label = document.getElementById(`label-${side}`);

    // Parse the src to get components
    const src = img.src;
    const pathMatch = src.match(/\/images\/([^/]+)\/([^/]+)\/(.+)$/);

    return {
        path: img.dataset.path,
        src: src,
        label: label.textContent
    };
}

/**
 * Undo the last battle
 */
async function undoLastBattle() {
    if (!lastBattle || !lastBattle.battle_id) {
        console.log('Nothing to undo');
        return;
    }

    if (isProcessing) return;
    isProcessing = true;

    try {
        const response = await fetch('/api/undo', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ battle_id: lastBattle.battle_id })
        });

        if (!response.ok) {
            throw new Error('Failed to undo');
        }

        const data = await response.json();

        if (data.success) {
            // Restore the previous matchup
            battleCount--;
            document.getElementById('battle-count').textContent = Math.max(0, battleCount);

            // Restore the undone matchup images
            if (data.matchup) {
                loadMatchup(data.matchup);
            }

            // Clear undo state (can only undo once)
            lastBattle = null;

            console.log('Undone battle:', data.battle_id);
        }

    } catch (error) {
        console.error('Error undoing battle:', error);
        alert('Error: ' + error.message);
    }

    isProcessing = false;
}

/**
 * Delete an image (no contest - no battle record)
 */
async function deleteImage(side) {
    if (isProcessing) return;

    const imagePath = currentImages[side].path;
    const otherSide = side === 'left' ? 'right' : 'left';
    const keepPath = currentImages[otherSide].path;

    // Confirm deletion
    if (!confirm('Delete this image? This cannot be undone.')) {
        return;
    }

    isProcessing = true;

    try {
        const response = await fetch('/api/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                delete_path: imagePath,
                keep_path: keepPath,
                exclude_recent: recentImages,
                ...scopeData
            })
        });

        if (!response.ok) {
            throw new Error('Failed to delete image');
        }

        const data = await response.json();

        if (data.success) {
            // Clear undo state (can't undo a delete)
            lastBattle = null;

            // Load next matchup (keeps the surviving image as one contestant)
            if (data.next) {
                // Preserve the kept image's current stats (don't reset them)
                const keptSide = otherSide;
                const keptStats = {
                    wins: parseInt(document.getElementById(`wins-${keptSide}`).textContent) || 0,
                    losses: parseInt(document.getElementById(`losses-${keptSide}`).textContent) || 0,
                    total_battles: parseInt(document.getElementById(`total-${keptSide}`).textContent) || 0
                };

                // Track new images in recent history
                addToRecentHistory(data.next.img1.path, data.next.img2.path);
                loadMatchup(data.next);

                // Restore the kept image's stats if it's still in the matchup
                // (check if the kept path matches either side after load)
                if (currentImages.left.path === keepPath) {
                    updateStats('left', keptStats);
                } else if (currentImages.right.path === keepPath) {
                    updateStats('right', keptStats);
                }
            } else {
                alert('No more matchups available!');
            }
        }

    } catch (error) {
        console.error('Error deleting image:', error);
        alert('Error: ' + error.message);
    }

    isProcessing = false;
}

/**
 * Load new matchup images
 */
function loadMatchup(matchup) {
    // Reset transforms
    resetView('left');
    resetView('right');

    // Update left image
    const imgLeft = document.getElementById('img-left');
    const labelLeft = document.getElementById('label-left');
    imgLeft.src = `/images/${matchup.img1.universe}/${matchup.img1.ip}/${matchup.img1.group_name}/${matchup.img1.filename}`;
    imgLeft.dataset.path = matchup.img1.path;
    currentImages.left.path = matchup.img1.path;
    labelLeft.textContent = `${matchup.img1.name} - ${matchup.img1.source}${matchup.img1.variant ? ` (${matchup.img1.variant})` : ''}`;

    // Update right image
    const imgRight = document.getElementById('img-right');
    const labelRight = document.getElementById('label-right');
    imgRight.src = `/images/${matchup.img2.universe}/${matchup.img2.ip}/${matchup.img2.group_name}/${matchup.img2.filename}`;
    imgRight.dataset.path = matchup.img2.path;
    currentImages.right.path = matchup.img2.path;
    labelRight.textContent = `${matchup.img2.name} - ${matchup.img2.source}${matchup.img2.variant ? ` (${matchup.img2.variant})` : ''}`;

    // Update stats from matchup data (no separate API call needed)
    updateStats('left', matchup.img1.stats);
    updateStats('right', matchup.img2.stats);
}

/**
 * Update stats display for a side
 */
function updateStats(side, stats) {
    document.getElementById(`wins-${side}`).textContent = stats?.wins ?? 0;
    document.getElementById(`losses-${side}`).textContent = stats?.losses ?? 0;
    document.getElementById(`total-${side}`).textContent = stats?.total_battles ?? 0;
}
