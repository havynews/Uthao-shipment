(function () {
  const input  = document.getElementById('trackInput');
  const button = document.getElementById('trackBtn');
  const result = document.getElementById('trackingResult');

  button.addEventListener('click', trackShipment);
  input.addEventListener('keypress', e => {
    if (e.key === 'Enter') trackShipment();
  });

  async function trackShipment() {
    const tracking = input.value.trim();

    if (!tracking) {
      alert("Enter tracking number");
      return;
    }

    result.innerHTML = loadingUI();

    try {
      const res = await fetch(`/api/track/${tracking}`);
      if (!res.ok) throw new Error("Not found");

      const data = await res.json();
      renderTracking(data);

    } catch (err) {
      result.innerHTML = `
        <div class="track-error">
          <i class="fas fa-exclamation-circle"></i>
          Shipment not found
        </div>`;
    }
  }

  function loadingUI() {
    return `<div class="track-loading">Tracking shipment...</div>`;
  }

  function renderTracking(s) {
    result.innerHTML = `
      <div class="track-card">
        <h2>${s.tracking_number}</h2>
        <div class="route">${s.origin} → ${s.destination}</div>
        <div class="status">${s.status}</div>
        <div class="eta">
          Estimated Delivery: ${formatDate(s.estimated_delivery)}
        </div>

        <div class="timeline">
          ${buildTimeline(s.events, s.status)}
        </div>
      </div>
    `;
  }

  function buildTimeline(events, shipmentStatus) {
    const statusOrder = [
      'Booking Created',
      'Picked Up',
      'In Transit',
      'Out for Delivery',
      'Delivered'
    ];

    const currentIdx = statusOrder.indexOf(shipmentStatus);

    return events.map(ev => {
      const evIdx = statusOrder.indexOf(ev.status);
      let state = 'pending';
      if (evIdx < currentIdx) state = 'completed';
      if (evIdx === currentIdx) state = 'current';

      return `
        <div class="timeline-item ${state}">
          <div class="dot"></div>
          <div>
            <div class="label">${ev.description || ev.status}</div>
            <div class="meta">
              ${ev.location || ''} 
              ${ev.timestamp ? formatDate(ev.timestamp) : ''}
            </div>
          </div>
        </div>
      `;
    }).join('');
  }

  function formatDate(d) {
    if (!d) return '—';
    const date = new Date(d);
    if (isNaN(date)) return d;
    return date.toLocaleString();
  }

})();