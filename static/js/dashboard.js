/* ═══════════════════════════════════════════
   UTHAO — Dashboard / Tracking JS
   Fetches data dynamically from Flask API
═══════════════════════════════════════════ */

(function () {
  'use strict';

  /* ── State ── */
  let allShipments = [];
  let activeFilter = 'all';
  let activeId     = null;

  /* ── DOM refs ── */
  const listEl   = document.getElementById('shipmentList');
  const detailEl = document.getElementById('detailPanel');

  /* ══════════════════════════════════════════
     API — fetch all shipments for current user
  ══════════════════════════════════════════ */

  async function loadShipments() {
    renderSkeletons();
    try {
      const res  = await fetch('/user/api/shipments');
      if (!res.ok) throw new Error('Failed to fetch');
      const data = await res.json();
      allShipments = data.shipments || [];
      renderList(allShipments);

      // Auto-select first
      if (allShipments.length > 0) {
        selectShipment(allShipments[0].tracking_number);
      } else {
        showNoSelection();
      }
    } catch (err) {
      console.error(err);
      listEl.innerHTML = `
        <div class="empty-state">
          <i class="fas fa-exclamation-circle"></i>
          <p>Could not load shipments</p>
          <a href="#" onclick="location.reload()">Retry</a>
        </div>`;
    }
  }

  /* ══════════════════════════════════════════
     API — fetch single shipment detail
  ══════════════════════════════════════════ */

  async function fetchDetail(tracking) {
    const res  = await fetch(`/user/api/shipments/${tracking}`);
    if (!res.ok) throw new Error('Not found');
    return res.json();
  }

  /* ══════════════════════════════════════════
     RENDER — skeleton placeholders
  ══════════════════════════════════════════ */

  function renderSkeletons() {
    listEl.innerHTML = Array(4).fill('').map(() => `
      <div class="sk-card">
        <div style="display:flex;gap:10px;align-items:center">
          <div class="skeleton" style="width:36px;height:36px;border-radius:9px;flex-shrink:0"></div>
          <div style="flex:1;display:flex;flex-direction:column;gap:6px">
            <div class="skeleton" style="height:12px;width:60%"></div>
            <div class="skeleton" style="height:10px;width:40%"></div>
          </div>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:flex-end;margin-top:4px">
          <div class="skeleton" style="height:10px;width:30%"></div>
          <div class="skeleton" style="height:20px;width:80px;border-radius:20px"></div>
        </div>
      </div>
    `).join('');
  }

  /* ══════════════════════════════════════════
     RENDER — shipment card list
  ══════════════════════════════════════════ */

  function renderList(shipments) {
    if (!shipments.length) {
      listEl.innerHTML = `
        <div class="empty-state">
          <i class="fas fa-box"></i>
          <p>No shipments found</p>
          <a href="/user/create-shipment">Create your first shipment →</a>
        </div>`;
      return;
    }

    listEl.innerHTML = shipments.map(s => shipmentCardHTML(s)).join('');

    // Attach click handlers
    listEl.querySelectorAll('.s-card').forEach(card => {
      card.addEventListener('click', () => {
        selectShipment(card.dataset.tracking);
      });
    });

    // Restore active highlight
    if (activeId) highlightCard(activeId);
  }

  function shipmentCardHTML(s) {
    const badge = statusBadge(s.status);
    const icon  = cargoIcon(s.commodity || s.cargo_type || '');
    return `
      <div class="s-card" data-tracking="${s.tracking_number}">
        <div class="sc-top">
          <div class="sc-icon"><i class="${icon}"></i></div>
          <div class="sc-meta">
            <div class="sc-tracking">${s.tracking_number}</div>
            <div class="sc-type">${s.commodity || s.cargo_type || 'General Cargo'}</div>
          </div>
          <i class="fas fa-chevron-right sc-arrow"></i>
        </div>
        <div class="sc-bottom">
          <div>
            <div class="sc-eta-label">Delivery ETA</div>
            <div class="sc-eta-date">${formatDate(s.estimated_delivery)}</div>
          </div>
          ${badge}
        </div>
      </div>`;
  }

  /* ══════════════════════════════════════════
     SELECT — load and render detail
  ══════════════════════════════════════════ */

  async function selectShipment(tracking) {
    activeId = tracking;
    highlightCard(tracking);
    renderDetailSkeleton();

    try {
      const s = await fetchDetail(tracking);
      renderDetail(s);
    } catch (err) {
      detailEl.innerHTML = `
        <div class="no-selection">
          <i class="fas fa-exclamation-circle"></i>
          <p>Could not load shipment details</p>
        </div>`;
    }
  }

  function highlightCard(tracking) {
    listEl.querySelectorAll('.s-card').forEach(c => {
      c.classList.toggle('active', c.dataset.tracking === tracking);
    });
  }

  /* ══════════════════════════════════════════
     RENDER — detail skeleton
  ══════════════════════════════════════════ */

  function renderDetailSkeleton() {
    detailEl.innerHTML = `
      <div class="detail-hdr">
        <div class="skeleton" style="height:10px;width:100px;margin-bottom:8px"></div>
        <div class="skeleton" style="height:22px;width:200px;margin-bottom:6px"></div>
        <div class="skeleton" style="height:12px;width:150px"></div>
      </div>
      <div class="skeleton map-box"></div>
      <div class="skeleton" style="height:70px;border-radius:var(--radius)"></div>
      <div class="skeleton" style="height:90px;border-radius:var(--radius)"></div>
      <div class="skeleton" style="height:180px;border-radius:var(--radius)"></div>
      <div class="skeleton" style="height:90px;border-radius:var(--radius)"></div>
    `;
  }

  /* ══════════════════════════════════════════
     RENDER — full detail panel
  ══════════════════════════════════════════ */

  function renderDetail(s) {
    const events = s.events || [];
    const recipient = s.recipient || { 
      name: 'Recipient', 
      company: '', 
      phone: '' 
    };

    detailEl.innerHTML = `
      <button class="detail-close" onclick="closeDetail()" title="Close">
        <i class="fas fa-times"></i>
      </button>

      <!-- Header -->
      <div class="detail-hdr fade-up" style="animation-delay:0s">
        <div class="d-label">Shipment number</div>
        <div class="d-tracking">${s.tracking_number}</div>
        <div class="d-route">
          <span>${s.origin}</span>
          <i class="fas fa-arrow-right"></i>
          <span>${s.destination}</span>
        </div>
      </div>

      <!-- Map -->
      <div class="map-box fade-up" style="animation-delay:0.05s">
        ${buildMap(s)}
      </div>

      <!-- Arrival -->
      <div class="arrival-card fade-up" style="animation-delay:0.1s">
        <div class="arrival-icon"><i class="fas fa-box-open"></i></div>
        <div>
          <div class="arrival-label">Your purchase will arrive</div>
          <div class="arrival-value">${arrivalText(s)} <strong>— ${s.delivery_time || '02:30 PM'}</strong></div>
          <div class="arrival-sub">Estimated package delivery: ${formatDate(s.estimated_delivery)}</div>
        </div>
      </div>

      <!-- Info card -->
      <div class="info-card fade-up" style="animation-delay:0.12s">
        <div class="info-card-meta">
          <div class="ic-tracking">${s.tracking_number}</div>
          <div class="ic-cargo">${s.commodity || s.cargo_type || 'General Cargo'}</div>
          <div class="ic-eta-label">Estimated delivery</div>
          <div class="ic-eta-val">${formatDate(s.estimated_delivery)}</div>
        </div>
        <div class="truck-visual">
          <i class="fas fa-truck"></i>
        </div>
      </div>

      <!-- Timeline -->
      <div class="timeline-card fade-up" style="animation-delay:0.15s">
        <h3><i class="fas fa-route"></i> Tracking Progress</h3>
        <div class="tl">
          ${buildTimeline(events, s.status)}
        </div>
      </div>

      <!-- Recipient -->
      <div class="recipient-card fade-up" style="animation-delay:0.18s">
        <!-- Recipient -->
          <div class="recipient-card fade-up" style="animation-delay:0.18s">
            <h3>Client Information</h3>

            <div class="recipient-row">
              <div class="recipient-av">
                <i class="fas fa-user"></i>
              </div>

              <div class="recipient-details">
                <div class="recipient-name">${recipient.name || '—'}</div>
                ${recipient.company ? `<div class="recipient-company">${recipient.company}</div>` : ''}

                <div class="recipient-meta">
                  ${recipient.phone ? `
                    <div class="recipient-line">
                      <i class="fas fa-phone"></i>
                      <span>${recipient.phone}</span>
                    </div>` : ''}

                  ${recipient.email ? `
                    <div class="recipient-line">
                      <i class="fas fa-envelope"></i>
                      <span>${recipient.email}</span>
                    </div>` : ''}

                  ${recipient.address ? `
                    <div class="recipient-line">
                      <i class="fas fa-map-marker-alt"></i>
                      <span>${recipient.address}</span>
                    </div>` : ''}
                </div>
              </div>
            </div>
          </div>
      </div>
    `;
  }

  /* ══════════════════════════════════════════
     BUILD — SVG Map
  ══════════════════════════════════════════ */

  function buildMap(s) {
    const progress = progressPercent(s.status);
    // Quadratic bezier: start(60,140) control(300,30) end(540,55)
    const cx = 60 + (540 - 60) * progress;
    const cy = 140 + (55  - 140) * progress - Math.sin(Math.PI * progress) * 60;

    return `
      <svg viewBox="0 0 600 190" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="mapBg" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#181818"/>
            <stop offset="100%" stop-color="#0d0d0d"/>
          </linearGradient>
          <filter id="mglow">
            <feGaussianBlur stdDeviation="3" result="b"/>
            <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
        </defs>

        <rect width="600" height="190" fill="url(#mapBg)"/>

        <!-- Grid -->
        <g stroke="rgba(255,255,255,0.025)" stroke-width="1">
          ${[40,80,120,160].map(y=>`<line x1="0" y1="${y}" x2="600" y2="${y}"/>`).join('')}
          ${[100,200,300,400,500].map(x=>`<line x1="${x}" y1="0" x2="${x}" y2="190"/>`).join('')}
        </g>

        <!-- Route glow -->
        <path d="M 60 140 Q 300 30 540 55"
              stroke="rgba(249,115,22,0.18)" stroke-width="10"
              fill="none" stroke-linecap="round"/>

        <!-- Route dashed -->
        <path class="route-anim"
              d="M 60 140 Q 300 30 540 55"
              stroke="#f97316" stroke-width="2.5" fill="none"
              stroke-dasharray="8,5" stroke-linecap="round"
              filter="url(#mglow)"/>

        <!-- Origin -->
        <circle cx="60" cy="140" r="6" fill="#444" stroke="#f97316" stroke-width="2"/>
        <circle cx="60" cy="140" r="11" fill="none" stroke="#f97316" stroke-width="1" opacity="0.35"/>
        <text x="60" y="158" text-anchor="middle" fill="#888" font-size="9" font-family="DM Sans">${s.origin_city || s.origin}</text>

        <!-- Destination -->
        <circle cx="540" cy="55" r="8" fill="#f97316" stroke="#fff" stroke-width="2" filter="url(#mglow)"/>
        <circle cx="540" cy="55" r="14" fill="none" stroke="#f97316" stroke-width="1" opacity="0.3"/>
        <circle cx="540" cy="55" r="20" fill="none" stroke="#f97316" stroke-width="0.5" opacity="0.12"/>
        <text x="540" y="73" text-anchor="middle" fill="#888" font-size="9" font-family="DM Sans">${s.destination_city || s.destination}</text>

        <!-- Current truck position -->
        <g class="truck-anim">
          <circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="9" fill="rgba(249,115,22,0.2)"/>
          <circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="5" fill="#f97316" stroke="#fff" stroke-width="1.5" filter="url(#mglow)"/>
        </g>

        <!-- Status label -->
        <rect x="220" y="10" width="160" height="20" rx="6"
              fill="rgba(249,115,22,0.12)" stroke="rgba(249,115,22,0.35)" stroke-width="1"/>
        <text x="300" y="24" text-anchor="middle" fill="#f97316"
              font-size="9" font-family="DM Sans" font-weight="600">${s.status}</text>
      </svg>`;
  }

  /* ══════════════════════════════════════════
     BUILD — Timeline
  ══════════════════════════════════════════ */

  const DEFAULT_EVENTS = [
    { label: 'Package successfully received',  status: 'completed', time: '08:45' },
    { label: 'Package being picked up',         status: 'completed', time: '08:30', note: '15 mins late' },
    { label: 'Package is out for delivery',     status: 'current',   time: 'Now' },
    { label: 'Package delivered',               status: 'pending',   time: '' },
  ];

  function buildTimeline(events, shipmentStatus) {
    const items = events.length ? mapEvents(events, shipmentStatus) : DEFAULT_EVENTS;
    return items.map(ev => `
      <div class="tl-item ${ev.status}">
        <div class="tl-dot-col"><div class="tl-dot"></div></div>
        <div class="tl-body">
          <div class="tl-label">${ev.label}</div>
          ${ev.time ? `
            <div class="tl-time">
              ${ev.time}
              ${ev.note ? `<span class="tl-pill">${ev.note}</span>` : ''}
            </div>` : ''}
        </div>
      </div>`).join('');
  }

  function mapEvents(events, shipmentStatus) {
    const statusOrder = ['Booking Created','Picked Up','In Transit','Out for Delivery','Delivered'];
    const currentIdx  = statusOrder.indexOf(shipmentStatus);

    return events.map((ev, i) => {
      const evIdx = statusOrder.indexOf(ev.status_label || ev.status);
      let state = 'pending';
      if (evIdx < currentIdx)  state = 'completed';
      if (evIdx === currentIdx) state = 'current';

      return {
        label: ev.description || ev.label,
        status: state,
        time: ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) : ev.time || '',
      };
    });
  }

  /* ══════════════════════════════════════════
     HELPERS
  ══════════════════════════════════════════ */

  function formatDate(d) {
    if (!d) return '—';
    const date = new Date(d);
    if (isNaN(date)) return d;
    return date.toLocaleDateString('en-GB', { day:'2-digit', month:'short', year:'2-digit' });
  }

  function arrivalText(s) {
    if (!s.estimated_delivery) return 'Soon';
    const eta  = new Date(s.estimated_delivery);
    const now  = new Date();
    const diff = Math.ceil((eta - now) / 86400000);
    if (diff <= 0) return 'Today';
    if (diff === 1) return 'Tomorrow';
    return formatDate(s.estimated_delivery);
  }

  function progressPercent(status) {
    const map = {
      'Booking Created': 0.05,
      'Picked Up':        0.25,
      'In Transit':       0.55,
      'Out for Delivery': 0.80,
      'Delivered':        1.00,
    };
    return map[status] ?? 0.5;
  }

  function statusBadge(status) {
    if (!status) return '';
    const map = {
      'Delivered':        ['badge-green',  'fa-check-circle', 'Delivered'],
      'In Transit':       ['badge-gray',   'fa-circle',       'In Transit'],
      'Out for Delivery': ['badge-orange', 'fa-circle',       'Out for Delivery'],
      'Booking Created':  ['badge-gray',   'fa-clock',        'Booking Created'],
      'Picked Up':        ['badge-gray',   'fa-circle',       'Picked Up'],
    };
    const [cls, icon, label] = map[status] || ['badge-gray', 'fa-circle', status];
    return `<span class="badge ${cls}"><i class="fas ${icon}" style="font-size:7px"></i>${label}</span>`;
  }

  function cargoIcon(type) {
    const t = (type || '').toLowerCase();
    if (t.includes('food'))   return 'fas fa-utensils';
    if (t.includes('elec'))   return 'fas fa-microchip';
    if (t.includes('pharm'))  return 'fas fa-pills';
    if (t.includes('chem'))   return 'fas fa-flask';
    if (t.includes('raw'))    return 'fas fa-cubes';
    return 'fas fa-box';
  }

  /* ── close detail ── */
  window.closeDetail = function () {
    activeId = null;
    listEl.querySelectorAll('.s-card').forEach(c => c.classList.remove('active'));
    showNoSelection();
  };

  function showNoSelection() {
    detailEl.innerHTML = `
      <div class="no-selection">
        <i class="fas fa-box"></i>
        <p>Select a shipment to view tracking details</p>
      </div>`;
  }

  /* ── Filter chips ── */
  document.querySelectorAll('.filter-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      activeFilter = chip.dataset.filter;

      const filtered = activeFilter === 'all'
        ? allShipments
        : allShipments.filter(s => s.status?.toLowerCase().replace(/ /g,'') === activeFilter);

      renderList(filtered);

      // Re-select active
      if (activeId) {
        const still = filtered.find(s => s.tracking_number === activeId);
        if (still) selectShipment(activeId);
        else { activeId = null; showNoSelection(); }
      }
    });
  });

  /* ── Global search hook ── */
  document.addEventListener('uthao:search', (e) => {
    const q = e.detail.toLowerCase().trim();
    const results = q
      ? allShipments.filter(s =>
          s.tracking_number?.toLowerCase().includes(q) ||
          s.origin?.toLowerCase().includes(q) ||
          s.destination?.toLowerCase().includes(q) ||
          s.commodity?.toLowerCase().includes(q))
      : allShipments;
    renderList(results);
  });

  /* ── Init ── */
  loadShipments();

})();