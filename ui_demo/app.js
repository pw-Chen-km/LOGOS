/* ═══════════════════════════════════════════════════════════════
   Research Graph UI — Application Logic
   ═══════════════════════════════════════════════════════════════ */

const API = 'http://localhost:5001/api';

// ── State ──────────────────────────────────────────────────────
let allPapers = [];
let allKeywords = [];
let selectedKeywords = new Set();
let currentPaperTitle = null;
let anatomyData = null;
let networkData = null;
let anatomySim = null;
let networkSim = null;

// Node type → color mapping
const NODE_COLORS = {
    Paper:                     'hsl(250, 80%, 65%)',
    Summary:                   'hsl(190, 70%, 55%)',
    Keyword:                   'hsl(160, 60%, 50%)',
    ResearchProblem:           'hsl(340, 70%, 60%)',
    PreviousLimitation:        'hsl(340, 55%, 50%)',
    UnderlyingResearchProblem: 'hsl(340, 55%, 45%)',
    Method:                    'hsl(35, 85%, 60%)',
    MethodDetail:              'hsl(35, 65%, 50%)',
    ReferredAlgorithm:         'hsl(35, 65%, 45%)',
    Experiment:                'hsl(270, 65%, 60%)',
    ExperimentAnalysis:        'hsl(270, 50%, 50%)',
    ComparedMethod:            'hsl(220, 55%, 55%)',
    Dataset:                   'hsl(145, 55%, 50%)',
};

const EDGE_COLORS = {
    TACKLES_SIMILAR_PROBLEM:    'hsl(25, 90%, 55%)',
    EVALUATED_ON_SAME_BENCHMARK:'hsl(145, 65%, 48%)',
    HAS_COMMON_BASELINE:        'hsl(220, 80%, 60%)',
};

const NODE_RADIUS = { 1: 28, 2: 18, 3: 12 };

// ── Initialization ─────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    loadStats();
    loadPapers();
    loadKeywords();
});

async function apiFetch(path, opts = {}) {
    const res = await fetch(`${API}${path}`, {
        headers: { 'Content-Type': 'application/json' },
        ...opts,
    });
    return res.json();
}

// ── Stats ──────────────────────────────────────────────────────
async function loadStats() {
    const s = await apiFetch('/stats');
    document.getElementById('stat-papers').textContent = s.papers;
    document.getElementById('stat-entities').textContent = s.entities;
    document.getElementById('stat-relations').textContent = s.relations;
}

// ── Papers List ────────────────────────────────────────────────
async function loadPapers() {
    allPapers = await apiFetch('/papers');
    renderPapers(allPapers);
}

function renderPapers(papers) {
    const grid = document.getElementById('papers-grid');
    document.getElementById('result-count').textContent = `${papers.length} paper${papers.length !== 1 ? 's' : ''}`;

    if (!papers.length) {
        grid.innerHTML = `
            <div class="empty-state" style="grid-column: 1 / -1;">
                <div class="icon">📭</div>
                <p>No papers found matching your filters.</p>
            </div>`;
        return;
    }

    grid.innerHTML = papers.map(p => `
        <div class="paper-card" onclick="openPaper('${escapeHtml(p.title)}')" id="card-${hashCode(p.title)}">
            <span class="year-badge">${p.year || 'Unknown'}</span>
            <h3>${escapeHtml(p.title)}</h3>
            <p class="claim">${escapeHtml(p.claim || '')}</p>
            <div class="keywords-row">
                ${(p.keywords || []).slice(0, 5).map(k => `<span class="keyword-badge">${escapeHtml(k)}</span>`).join('')}
                ${(p.keywords || []).length > 5 ? `<span class="keyword-badge">+${p.keywords.length - 5}</span>` : ''}
            </div>
            <span class="arrow-icon">→</span>
        </div>
    `).join('');
}

// ── Keywords & Filter ──────────────────────────────────────────
async function loadKeywords() {
    allKeywords = await apiFetch('/keywords');
    renderKeywords(allKeywords);

    // Search filter
    document.getElementById('keyword-search').addEventListener('input', e => {
        const q = e.target.value.toLowerCase();
        const filtered = allKeywords.filter(k => k.name.toLowerCase().includes(q));
        renderKeywords(filtered);
    });
}

function renderKeywords(keywords) {
    const list = document.getElementById('keyword-list');
    list.innerHTML = keywords.map(k => `
        <label class="keyword-item ${selectedKeywords.has(k.name) ? 'selected' : ''}" id="kw-${hashCode(k.name)}">
            <input type="checkbox" ${selectedKeywords.has(k.name) ? 'checked' : ''} onchange="toggleKeyword('${escapeHtml(k.name)}', this.checked)">
            <span>${escapeHtml(k.name)}</span>
            <span class="keyword-count">${k.count}</span>
        </label>
    `).join('');
}

function toggleKeyword(name, checked) {
    if (checked) selectedKeywords.add(name);
    else selectedKeywords.delete(name);
    renderKeywords(allKeywords.filter(k => {
        const q = document.getElementById('keyword-search').value.toLowerCase();
        return k.name.toLowerCase().includes(q);
    }));
}

async function applyFilters() {
    if (!selectedKeywords.size) {
        renderPapers(allPapers);
        return;
    }
    const papers = await apiFetch('/papers/filter', {
        method: 'POST',
        body: JSON.stringify({ keywords: [...selectedKeywords] }),
    });
    renderPapers(papers);
}

function clearFilters() {
    selectedKeywords.clear();
    renderKeywords(allKeywords);
    renderPapers(allPapers);
}

// ── Navigation ─────────────────────────────────────────────────
function showDashboard() {
    document.getElementById('view-dashboard').classList.add('active');
    document.getElementById('view-paper').classList.remove('active');

    // Clean up graph simulations
    if (anatomySim) { anatomySim.stop(); anatomySim = null; }
    if (networkSim) { networkSim.stop(); networkSim = null; }
    currentPaperTitle = null;

    // Update nav
    updateNavTabs();
}

function showPaperView() {
    document.getElementById('view-dashboard').classList.remove('active');
    document.getElementById('view-paper').classList.add('active');
    updateNavTabs();
}

function updateNavTabs() {
    const nav = document.getElementById('topbar-nav');
    const dashBtn = document.getElementById('nav-dashboard');
    dashBtn.className = document.getElementById('view-dashboard').classList.contains('active') ? 'active' : '';

    // Remove old paper tabs
    nav.querySelectorAll('.paper-tab-btn').forEach(b => b.remove());

    if (currentPaperTitle) {
        const btn = document.createElement('button');
        btn.className = 'paper-tab-btn active';
        btn.textContent = `📄 ${currentPaperTitle.substring(0, 30)}…`;
        btn.onclick = () => showPaperView();
        nav.appendChild(btn);
    }
}

function switchPaperTab(tab) {
    document.querySelectorAll('.anatomy-tabs button').forEach(b => b.classList.remove('active'));
    document.querySelector(`.anatomy-tabs button[data-tab="${tab}"]`).classList.add('active');

    document.getElementById('tab-content-anatomy').style.display = tab === 'anatomy' ? 'flex' : 'none';
    document.getElementById('tab-content-network').style.display = tab === 'network' ? 'flex' : 'none';

    if (tab === 'network' && currentPaperTitle && !networkData) {
        loadNetworkGraph(currentPaperTitle);
    }
}

// ═══════════════════════════════════════════════════════════════
//  View 2: Paper Anatomy (Accordion & Progressive Disclosure)
// ═══════════════════════════════════════════════════════════════

async function renderAnatomyCard(title) {
    const container = document.getElementById('anatomy-card-container');
    container.innerHTML = `<div class="anatomy-loading"><div class="spinner"></div></div>`;

    let overview;
    try {
        overview = await apiFetch(`/paper/${encodeURIComponent(title)}/overview`);
    } catch (e) {
        container.innerHTML = `<div class="empty-state">Failed to load paper details.</div>`;
        return;
    }

    if (overview.error) {
        container.innerHTML = `<div class="empty-state">${escapeHtml(overview.error)}</div>`;
        return;
    }

    // 1. Build Keyword Tags
    const tagsHtml = (overview.keywords || []).map(k =>
        `<span class="anatomy-keyword-tag">${escapeHtml(k)}</span>`
    ).join('');

    // 2. Build the Overview Card Header
    let html = `
        <div class="anatomy-overview-card">
            <div style="font-family:'JetBrains Mono', monospace; font-size:0.8rem; color:var(--text-accent); margin-bottom:8px;">
                ${escapeHtml(overview.year || 'Unknown Year')}
            </div>
            <div class="anatomy-claim">
                ${escapeHtml(overview.claim || 'No summary available.')}
            </div>
            ${tagsHtml ? `<div class="anatomy-keyword-row">${tagsHtml}</div>` : ''}
        </div>
    `;

    // 3. Dimension Selector Row
    html += `
        <div class="dimension-row">
            <button class="dim-btn" data-dim="problem" onclick="loadAnatomySection('${escapeHtml(title)}', 'problem')">
                <span class="dim-icon">🎯</span> Research Problem
            </button>
            <button class="dim-btn" data-dim="method" onclick="loadAnatomySection('${escapeHtml(title)}', 'method')">
                <span class="dim-icon">⚙️</span> Method
            </button>
            <button class="dim-btn" data-dim="experiment" onclick="loadAnatomySection('${escapeHtml(title)}', 'experiment')">
                <span class="dim-icon">📊</span> Experiment
            </button>
        </div>
        <div id="anatomy-section-content"></div>
    `;

    container.innerHTML = html;
}

// Override openPaper to call our new render function instead of the old D3 one
async function openPaper(title) {
    currentPaperTitle = title;
    networkData = null;
    showPaperView();
    switchPaperTab('anatomy');

    // Set header
    document.getElementById('paper-title-display').textContent = title;
    const paper = allPapers.find(p => p.title === title);
    document.getElementById('paper-meta-row').innerHTML = paper
        ? `<span>📅 ${escapeHtml(paper.year || 'Unknown')}</span><span>🏷️ ${(paper.keywords || []).length} keywords</span>`
        : '';

    // Render the new card
    renderAnatomyCard(title);
}

// ── Lazy Load Sections ─────────────────────────────────────────

async function loadAnatomySection(title, dim) {
    // Update active button state
    document.querySelectorAll('.dim-btn').forEach(b => b.classList.remove('active'));
    document.querySelector(`.dim-btn[data-dim="${dim}"]`).classList.add('active');

    const contentDiv = document.getElementById('anatomy-section-content');
    contentDiv.innerHTML = `
        <div class="accordion-panel">
            <div class="accordion-section">
                <div class="skel-line" style="width: 40%"></div>
                <div class="skel-line" style="width: 80%"></div>
                <div class="skel-line" style="width: 60%"></div>
            </div>
        </div>
    `;

    try {
        const data = await apiFetch(`/paper/${encodeURIComponent(title)}/section/${dim}`);
        if (data.error) {
            contentDiv.innerHTML = `<div class="accordion-panel"><div class="accordion-section" style="color:var(--text-muted)">No data found for this section.</div></div>`;
            return;
        }

        let html = '';
        const dotColor = dim === 'problem' ? 'hsl(340,70%,60%)' : dim === 'method' ? 'hsl(35,85%,60%)' : 'hsl(270,65%,60%)';
        const titleText = dim === 'problem' ? 'Research Problem Analysis' : dim === 'method' ? 'Methodology Details' : 'Experimental Results';

        html += `
        <div class="accordion-panel">
            <div class="accordion-panel-header">
                <div class="accordion-panel-dot" style="background:${dotColor}"></div>
                <div class="accordion-panel-title">${titleText}</div>
            </div>`;

        if (dim === 'problem') {
            if (data.summary) html += buildSection('Core Problem', data.summary, true);
            if (data.previous_limitation) html += buildSection('Previous Limitations', data.previous_limitation, true);
            if (data.underlying_problem) html += buildSection('Underlying Root Cause', data.underlying_problem, true);
        }
        else if (dim === 'method') {
            if (data.overview) html += buildSection('Method Overview', data.overview, true);
            if (data.detail) html += buildSection('Implementation Details', data.detail, true);
            if (data.algorithms) {
                const algos = Array.isArray(data.algorithms) ? data.algorithms : [data.algorithms];
                const chips = algos.map(a => `<span class="chip algo">${escapeHtml(a)}</span>`).join('');
                html += `<div class="accordion-section">
                            <div class="accordion-section-label">Referred Algorithms</div>
                            <div class="chip-row">${chips}</div>
                         </div>`;
            }
        }
        else if (dim === 'experiment') {
            if (data.result) html += buildSection('Key Results', data.result, true);
            if (data.design) html += buildSection('Experimental Design', data.design, true);
            if (data.comprehensive_analysis) html += buildSection('Comprehensive Analysis', data.comprehensive_analysis, true, true);
            
            if (data.datasets && data.datasets.length > 0) {
                const chips = data.datasets.map(d => `<span class="chip dataset">${escapeHtml(d)}</span>`).join('');
                html += `<div class="accordion-section">
                            <div class="accordion-section-label">Datasets Used</div>
                            <div class="chip-row">${chips}</div>
                         </div>`;
            }
            if (data.compared_methods && data.compared_methods.length > 0) {
                const chips = data.compared_methods.map(d => `<span class="chip method">${escapeHtml(d)}</span>`).join('');
                html += `<div class="accordion-section">
                            <div class="accordion-section-label">Compared Baselines</div>
                            <div class="chip-row">${chips}</div>
                         </div>`;
            }
        }

        html += `</div>`; // end panel
        contentDiv.innerHTML = html;

    } catch (e) {
        contentDiv.innerHTML = `<div class="accordion-panel"><div class="accordion-section" style="color:red">Error loading section.</div></div>`;
    }
}

function buildSection(label, text, escape = true, isMarkdown = false) {
    if (!text) return '';
    let content = isMarkdown ? marked.parse(String(text)) : escapeHtml(String(text));
    return `
        <div class="accordion-section">
            <div class="accordion-section-label">${escapeHtml(label)}</div>
            <div class="accordion-text ${isMarkdown ? 'markdown-body' : ''}">${content}</div>
        </div>
    `;
}


// ═══════════════════════════════════════════════════════════════
//  View 3: Paper Exploration (Hub & Spoke Dashboard)
// ═══════════════════════════════════════════════════════════════

async function loadNetworkGraph(title) {
    networkData = await apiFetch(`/paper/${encodeURIComponent(title)}/relations`);
    renderExplorationView(networkData, title);
}

function renderExplorationView(data, hubTitle) {
    const container = document.getElementById('exploration-container');
    
    // Group all edges by related paper
    const relatedMap = new Map(); // targetTitle -> { node_info, connections: [] }
    
    // Find hub node info
    const hubNode = data.nodes.find(n => n.id === hubTitle) || { id: hubTitle, properties: {} };
    
    const edgeMap = new Map(); // Key: Hub-Related-Type, Value: Edge object
    data.edges.forEach(e => {
        const sourceId = typeof e.source === 'string' ? e.source : e.source.id;
        const targetId = typeof e.target === 'string' ? e.target : e.target.id;
        
        const isSourceHub = sourceId === hubTitle;
        const relatedId = isSourceHub ? targetId : sourceId;
        
        if (relatedId === hubTitle) return; 

        const edgeKey = `${hubTitle}|||${relatedId}|||${e.type}`;
        
        // Pick the edge that has properties (LLM reasoning). 
        // If we already have one with properties, don't overwrite it with one that doesn't.
        if (!edgeMap.has(edgeKey)) {
            edgeMap.set(edgeKey, e);
        } else {
            const existing = edgeMap.get(edgeKey);
            const hasProps = (obj) => obj.properties && Object.values(obj.properties).some(v => v && String(v).length > 0);
            if (!hasProps(existing) && hasProps(e)) {
                edgeMap.set(edgeKey, e);
            }
        }
    });

    // Populate relatedMap from deduplicated edges
    for (const e of edgeMap.values()) {
        const sourceId = typeof e.source === 'string' ? e.source : e.source.id;
        const relatedId = (sourceId === hubTitle) ? 
            (typeof e.target === 'string' ? e.target : e.target.id) : sourceId;

        if (!relatedMap.has(relatedId)) {
            const relNode = data.nodes.find(n => n.id === relatedId) || { id: relatedId };
            relatedMap.set(relatedId, { node: relNode, connections: [] });
        }
        relatedMap.get(relatedId).connections.push(e);
    }
    
    // Render Hub Header
    let html = `
        <div class="exploration-hub-header">
            <div class="exploration-hub-label">📍 Current Exploration Hub</div>
            <div class="exploration-hub-card">
                <div class="exploration-hub-title">${escapeHtml(hubTitle)}</div>
                <div style="font-size:0.9rem; color:var(--text-secondary);">
                    ${hubNode.properties?.year ? `📅 ${escapeHtml(hubNode.properties.year)}` : '📅 Unknown'}
                </div>
            </div>
        </div>
        <div class="exploration-spokes-header">
            <span>Connected Literature (${relatedMap.size} papers found)</span>
        </div>
    `;
    
    if (relatedMap.size === 0) {
        html += `<div class="empty-state"><div class="icon">🔗</div><p>No cross-paper relationships found for this paper.</p></div>`;
        container.innerHTML = html;
        return;
    }
    
    // Render Related Papers (Spokes)
    html += `<div class="exploration-spokes-grid">`;
    
    for (const [relId, relData] of relatedMap.entries()) {
        const conns = relData.connections;
        
        // Build Badges
        const badgesHtml = conns.map(c => {
            let badgeClass = 'problem'; // default fallback
            let icon = '🔗';
            let label = c.type.replace(/_/g, ' ');
            
            if (c.type === 'TACKLES_SIMILAR_PROBLEM') { badgeClass = 'problem'; icon = '🎯'; label = 'Tackles Similar Problem'; }
            if (c.type === 'EVALUATED_ON_SAME_BENCHMARK') { badgeClass = 'benchmark'; icon = '📊'; label = 'Same Benchmark'; }
            if (c.type === 'HAS_COMMON_BASELINE') { badgeClass = 'baseline'; icon = '⚖️'; label = 'Common Baseline'; }
            
            return `<span class="explore-badge ${badgeClass}">${icon} ${label}</span>`;
        }).join('');
        
        // Build Details (Reasons)
        const reasonsHtml = conns.map(c => {
            let reasonText = '';
            let reasonTitle = c.type.replace(/_/g, ' ');
            
            const p = c.properties || {};
            
            if (p.comprehensive_analysis) {
                reasonText = marked.parse(String(p.comprehensive_analysis));
            } else if (p.shared_core_issue) {
                reasonText = `<strong>Core Issue:</strong> ${escapeHtml(String(p.shared_core_issue))}`;
                if (p.approach_contrast) {
                    reasonText += `<br><br><strong>Approach Contrast:</strong> <em>${escapeHtml(String(p.approach_contrast))}</em>`;
                }
            } else if (p.micro_comparison_report) {
                reasonText = marked.parse(String(p.micro_comparison_report));
                if (p.shared_datasets) {
                    reasonText = `<strong>Shared Datasets:</strong> ${escapeHtml(String(p.shared_datasets))}<br><br>` + reasonText;
                }
            } else if (p.who_won) {
                reasonText = `<strong>Relative Performance:</strong> ${escapeHtml(String(p.who_won))}`;
                if (p.shared_baselines) {
                    reasonText = `<strong>Shared Baselines:</strong> ${escapeHtml(String(p.shared_baselines))}<br><br>` + reasonText;
                }
            } else if (p.reasoning) {
                reasonText = escapeHtml(String(p.reasoning)).replace(/\n/g, '<br>');
            } else if (p.similarity_score) {
                reasonText = `Cosine similarity score: ${Number(p.similarity_score).toFixed(3)}`;
            } else if (p.name) {
                reasonText = `Shared element: <strong>${escapeHtml(p.name)}</strong>`;
            } else {
                reasonText = `<em>Implicit structural connection.</em>`;
            }
            
            return `
                <div class="reason-item">
                    <div class="reason-label">${reasonTitle} DETAILS</div>
                    <div class="reason-text markdown-body">${reasonText}</div>
                </div>
            `;
        }).join('');
        
        html += `
            <div class="explore-card">
                <div class="explore-card-header">
                    <div class="explore-card-title">${escapeHtml(relId)}</div>
                    <div class="explore-badges">${badgesHtml}</div>
                </div>
                <div class="explore-reasons">
                    ${reasonsHtml}
                </div>
                <div class="explore-actions">
                    <button class="btn-explore primary" onclick="recenterOnPaper('${escapeHtml(relId)}')">
                        📍 Explore Connections
                    </button>
                    <button class="btn-explore secondary" onclick="openPaper('${escapeHtml(relId)}')">
                        🔬 Open Anatomy View
                    </button>
                </div>
            </div>
        `;
    }
    
    html += `</div>`;
    container.innerHTML = html;
}

async function recenterOnPaper(title) {
    currentPaperTitle = title;
    document.getElementById('paper-title-display').textContent = title;
    const paper = allPapers.find(p => p.title === title);
    document.getElementById('paper-meta-row').innerHTML = paper
        ? `<span>📅 ${escapeHtml(paper.year || 'Unknown')}</span><span>🏷️ ${(paper.keywords || []).length} keywords</span>`
        : '';
    updateNavTabs();

    networkData = await apiFetch(`/paper/${encodeURIComponent(title)}/relations`);
    renderExplorationView(networkData, title);
}

// ── Tooltip ────────────────────────────────────────────────────
function showTooltip(event, text) {
    const tip = document.getElementById('node-tooltip');
    tip.textContent = text;
    tip.style.left = (event.clientX + 12) + 'px';
    tip.style.top = (event.clientY - 30) + 'px';
    tip.classList.add('show');
}

function hideTooltip() {
    document.getElementById('node-tooltip').classList.remove('show');
}

// ── Utilities ──────────────────────────────────────────────────
function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function truncate(str, len) {
    if (!str) return '';
    return str.length > len ? str.substring(0, len) + '…' : str;
}

function hashCode(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        const chr = str.charCodeAt(i);
        hash = ((hash << 5) - hash) + chr;
        hash |= 0;
    }
    return Math.abs(hash);
}

function idOf(d) {
    return typeof d === 'string' ? d : (d.id || d);
}
