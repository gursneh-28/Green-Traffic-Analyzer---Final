"""
dashboard.py
============
Flask-SocketIO dashboard for the Green Traffic Analyzer.

Architecture
------------
  create_app(dashboard_state, state_lock)
      Returns (app, socketio).  The live_simulation thread writes to
      dashboard_state; a background SocketIO task pushes updates to all
      connected browsers every second.

  Standalone mode  (python dashboard.py)
      Starts with a built-in demo state so you can preview the UI without
      running the full simulation.
"""

import json
import logging
import os
import sys
import threading
import time
from datetime import datetime

from flask import Flask, render_template_string
from flask_socketio import SocketIO, emit

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HTML / CSS / JS template  (single-file, no external template folder needed)
# ---------------------------------------------------------------------------
DASHBOARD_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Green Traffic Analyzer</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  /* ── Design tokens ── */
  :root {
    --bg:          #0b0f0e;
    --surface:     #131918;
    --surface2:    #1a2120;
    --border:      #243330;
    --green:       #00e57a;
    --green-dim:   #00915c;
    --yellow:      #f5c842;
    --red:         #ff4f4f;
    --red-dim:     #8b2222;
    --text:        #e8f5f0;
    --muted:       #6b8a82;
    --car:         #4fc3f7;
    --motorcycle:  #ce93d8;
    --truck:       #ffb74d;
    --bus:         #81c784;
    --font-mono:   'JetBrains Mono', 'Fira Mono', monospace;
    --font-sans:   'Inter', 'Segoe UI', sans-serif;
    --radius:      10px;
    --radius-lg:   16px;
  }

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--font-sans);
    min-height: 100vh;
    padding: 20px;
  }

  /* ── Header ── */
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 24px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--border);
  }
  .logo {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .logo-icon {
    width: 40px; height: 40px;
    background: var(--green);
    border-radius: 10px;
    display: grid;
    place-items: center;
    font-size: 22px;
  }
  .logo h1 {
    font-size: 1.25rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: var(--text);
  }
  .logo p {
    font-size: 0.72rem;
    color: var(--muted);
    margin-top: 1px;
  }
  .header-meta {
    text-align: right;
    font-size: 0.75rem;
    color: var(--muted);
    font-family: var(--font-mono);
  }
  #live-dot {
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--green);
    margin-right: 5px;
    animation: pulse 1.4s infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.3; }
  }

  /* ── Grid layout ── */
  .grid {
    display: grid;
    gap: 16px;
  }
  .grid-top    { grid-template-columns: repeat(4, 1fr); }
  .grid-middle { grid-template-columns: 1fr 1fr 1fr; margin-top: 16px; }
  .grid-bottom { grid-template-columns: 1fr 1fr;     margin-top: 16px; }

  /* ── Cards ── */
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 18px 20px;
  }
  .card-label {
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--muted);
    margin-bottom: 6px;
  }
  .card-value {
    font-size: 1.8rem;
    font-weight: 700;
    font-family: var(--font-mono);
    line-height: 1;
  }
  .card-sub {
    font-size: 0.72rem;
    color: var(--muted);
    margin-top: 4px;
  }
  .card-value.green  { color: var(--green); }
  .card-value.yellow { color: var(--yellow); }
  .card-value.red    { color: var(--red); }

  /* ── Intersection diagram ── */
  .intersection-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 24px;
  }
  .intersection {
    position: relative;
    width: 220px;
    height: 220px;
  }
  /* Road strips */
  .road-h, .road-v {
    position: absolute;
    background: var(--surface2);
    border: 1px solid var(--border);
  }
  .road-h { top: 50%; left: 0; right: 0; height: 60px; transform: translateY(-50%); }
  .road-v { left: 50%; top: 0; bottom: 0; width: 60px; transform: translateX(-50%); }
  /* Centre box */
  .road-center {
    position: absolute;
    top: 50%; left: 50%;
    width: 60px; height: 60px;
    background: var(--border);
    transform: translate(-50%, -50%);
  }
  /* Direction labels */
  .dir-label {
    position: absolute;
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: var(--muted);
    text-align: center;
    width: 50px;
  }
  .dir-label.north { top: 4px;  left: 50%; transform: translateX(-50%); }
  .dir-label.south { bottom: 4px; left: 50%; transform: translateX(-50%); }
  .dir-label.east  { right: 4px; top: 50%; transform: translateY(-50%); }
  .dir-label.west  { left: 4px;  top: 50%; transform: translateY(-50%); }
  /* Signal boxes on each arm */
  .sig-box {
    position: absolute;
    width: 44px;
    height: 44px;
    border-radius: 8px;
    border: 2px solid var(--border);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    transition: background 0.3s, border-color 0.3s;
    font-size: 0.58rem;
    font-weight: 700;
    letter-spacing: 0.04em;
  }
  .sig-box .sig-count {
    font-size: 1rem;
    font-family: var(--font-mono);
    line-height: 1;
  }
  .sig-box.green-phase  { background: #003d28; border-color: var(--green); color: var(--green); }
  .sig-box.yellow-phase { background: #3d3000; border-color: var(--yellow); color: var(--yellow); }
  .sig-box.red-phase    { background: #1a0606; border-color: var(--red-dim); color: var(--muted); }
  /* Position each signal arm box */
  .sig-north { top: 28px;   left: 50%; transform: translateX(-50%); }
  .sig-south { bottom: 28px; left: 50%; transform: translateX(-50%); }
  .sig-east  { right: 28px; top: 50%; transform: translateY(-50%); }
  .sig-west  { left: 28px;  top: 50%; transform: translateY(-50%); }

  /* Countdown ring */
  .countdown-wrap {
    margin-top: 20px;
    text-align: center;
  }
  .countdown-ring {
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 80px; height: 80px;
  }
  .countdown-ring svg {
    position: absolute;
    top: 0; left: 0;
    transform: rotate(-90deg);
  }
  .countdown-ring circle {
    fill: none;
    stroke-width: 5;
    transition: stroke-dashoffset 0.9s linear, stroke 0.3s;
  }
  .countdown-ring circle.track { stroke: var(--border); }
  .countdown-ring circle.fill  { stroke: var(--green); }
  .countdown-number {
    font-size: 1.6rem;
    font-family: var(--font-mono);
    font-weight: 700;
    color: var(--green);
    position: relative;
  }
  .countdown-label {
    font-size: 0.65rem;
    color: var(--muted);
    margin-top: 4px;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }

  /* ── Phase plan table ── */
  .phase-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
  .phase-table th {
    text-align: left;
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
    padding: 6px 8px;
    border-bottom: 1px solid var(--border);
  }
  .phase-table td { padding: 8px 8px; border-bottom: 1px solid var(--border); }
  .phase-table tr:last-child td { border-bottom: none; }
  .phase-table tr.active-row td { background: #0d2b1e; }
  .phase-table .bar-cell { width: 100px; }
  .bar-track {
    width: 100%;
    height: 6px;
    background: var(--surface2);
    border-radius: 3px;
    overflow: hidden;
  }
  .bar-fill {
    height: 100%;
    border-radius: 3px;
    background: var(--green);
    transition: width 0.5s;
  }
  .badge {
    display: inline-block;
    padding: 2px 7px;
    border-radius: 4px;
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.06em;
  }
  .badge.green  { background: #003d28; color: var(--green); }
  .badge.red    { background: #1a0606; color: var(--red); }
  .badge.yellow { background: #3d3000; color: var(--yellow); }

  /* ── Vehicle breakdown ── */
  .breakdown-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    margin-top: 12px;
  }
  .cam-box {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 12px;
  }
  .cam-box .cam-name {
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 8px;
    color: var(--muted);
  }
  .type-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 0.75rem;
    margin-bottom: 4px;
  }
  .type-dot {
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 50%;
    margin-right: 5px;
  }
  .dot-car        { background: var(--car); }
  .dot-motorcycle { background: var(--motorcycle); }
  .dot-truck      { background: var(--truck); }
  .dot-bus        { background: var(--bus); }
  .type-count {
    font-family: var(--font-mono);
    font-weight: 600;
  }

  /* ── Emission panel ── */
  .emission-stat {
    display: flex;
    align-items: flex-end;
    gap: 6px;
    margin-top: 14px;
  }
  .emission-val {
    font-size: 2.2rem;
    font-family: var(--font-mono);
    font-weight: 700;
    color: var(--green);
    line-height: 1;
  }
  .emission-unit {
    font-size: 0.8rem;
    color: var(--muted);
    padding-bottom: 4px;
  }
  .emission-row {
    display: flex;
    justify-content: space-between;
    font-size: 0.78rem;
    padding: 7px 0;
    border-bottom: 1px solid var(--border);
    color: var(--muted);
  }
  .emission-row:last-child { border-bottom: none; }
  .emission-row span:last-child {
    font-family: var(--font-mono);
    color: var(--text);
    font-weight: 600;
  }

  /* ── Chart ── */
  .chart-wrap { position: relative; height: 180px; margin-top: 12px; }

  /* ── Section title ── */
  .section-title {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--muted);
    margin-bottom: 14px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .section-title::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--border);
  }

  @media (max-width: 900px) {
    .grid-top, .grid-middle, .grid-bottom {
      grid-template-columns: 1fr 1fr;
    }
  }
  @media (max-width: 580px) {
    .grid-top, .grid-middle, .grid-bottom {
      grid-template-columns: 1fr;
    }
  }
</style>
</head>
<body>

<!-- ── Header ── -->
<header>
  <div class="logo">
    <div class="logo-icon">🚦</div>
    <div>
      <h1>Green Traffic Analyzer</h1>
      <p>Adaptive signal control · Emission reduction · Real-time monitoring</p>
    </div>
  </div>
  <div class="header-meta">
    <span id="live-dot"></span>LIVE
    <div id="hdr-time">--:--:--</div>
    <div id="hdr-cycle">Cycle —</div>
  </div>
</header>

<!-- ── Top KPI row ── -->
<div class="grid grid-top">
  <div class="card">
    <div class="card-label">Queue Reduction vs Fixed</div>
    <div class="card-value green" id="kpi-efficiency">—</div>
    <div class="card-sub">less vehicles waiting next cycle</div>
  </div>
  <div class="card">
    <div class="card-label">CO₂ Saved · This Cycle</div>
    <div class="card-value green" id="kpi-co2">—</div>
    <div class="card-sub">grams</div>
  </div>
  <div class="card">
    <div class="card-label">Fuel Saved · This Cycle</div>
    <div class="card-value yellow" id="kpi-fuel">—</div>
    <div class="card-sub">millilitres</div>
  </div>
  <div class="card">
    <div class="card-label">Active Phase</div>
    <div class="card-value green" id="kpi-phase">—</div>
    <div class="card-sub" id="kpi-phase-state">waiting…</div>
  </div>
</div>

<!-- ── Middle row ── -->
<div class="grid grid-middle">

  <!-- Intersection diagram + countdown -->
  <div class="card intersection-card">
    <div class="section-title">Intersection</div>
    <div class="intersection">
      <div class="road-h"></div>
      <div class="road-v"></div>
      <div class="road-center"></div>

      <div class="dir-label north">N</div>
      <div class="dir-label south">S</div>
      <div class="dir-label east">E</div>
      <div class="dir-label west">W</div>

      <div class="sig-box red-phase sig-north" id="sig-camera_1">
        <span class="sig-count" id="sig-count-camera_1">0</span>
        <span>N</span>
      </div>
      <div class="sig-box red-phase sig-south" id="sig-camera_3">
        <span class="sig-count" id="sig-count-camera_3">0</span>
        <span>S</span>
      </div>
      <div class="sig-box red-phase sig-east" id="sig-camera_2">
        <span class="sig-count" id="sig-count-camera_2">0</span>
        <span>E</span>
      </div>
      <div class="sig-box red-phase sig-west" id="sig-camera_4">
        <span class="sig-count" id="sig-count-camera_4">0</span>
        <span>W</span>
      </div>
    </div>

    <div class="countdown-wrap">
      <div class="countdown-ring">
        <svg width="80" height="80" viewBox="0 0 80 80">
          <circle class="track" cx="40" cy="40" r="36" />
          <circle class="fill"  cx="40" cy="40" r="36"
            id="ring-fill"
            stroke-dasharray="226.2"
            stroke-dashoffset="0"/>
        </svg>
        <span class="countdown-number" id="countdown-num">—</span>
      </div>
      <div class="countdown-label" id="countdown-label">seconds remaining</div>
    </div>
  </div>

  <!-- Phase plan table -->
  <div class="card">
    <div class="section-title">Phase Plan · This Cycle</div>
    <table class="phase-table" id="phase-table">
      <thead>
        <tr>
          <th>Direction</th>
          <th>Pressure</th>
          <th>Green</th>
          <th>Carryover</th>
          <th class="bar-cell">Allocation</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody id="phase-tbody">
        <tr><td colspan="6" style="color:var(--muted);font-size:0.8rem;padding:12px 8px">Waiting for first cycle…</td></tr>
      </tbody>
    </table>
  </div>

  <!-- Emission savings panel -->
  <div class="card">
    <div class="section-title">Emission Savings</div>
    <div class="emission-stat">
      <span class="emission-val" id="em-co2-total">0</span>
      <span class="emission-unit">g CO₂ saved (total)</span>
    </div>
    <div style="margin-top:20px">
      <div class="emission-row">
        <span>Fuel saved (total)</span>
        <span id="em-fuel-total">0 mL</span>
      </div>
      <div class="emission-row">
        <span>CO₂ this cycle</span>
        <span id="em-co2-cycle">0 g</span>
      </div>
      <div class="emission-row">
        <span>Fuel this cycle</span>
        <span id="em-fuel-cycle">0 mL</span>
      </div>
      <div class="emission-row">
        <span>Cycles completed</span>
        <span id="em-cycles">0</span>
      </div>
      <div class="emission-row">
        <span>Avg queue reduction</span>
        <span id="em-avg-eff">—</span>
      </div>
    </div>
    <!-- mini equivalence line -->
    <div style="margin-top:16px;padding:10px;background:var(--surface2);border-radius:8px;font-size:0.75rem;color:var(--muted)">
      ≈ <span id="em-equiv" style="color:var(--green);font-weight:600">—</span>
      km of car driving avoided
    </div>
  </div>

</div>

<!-- ── Bottom row ── -->
<div class="grid grid-bottom">

  <!-- Vehicle type breakdown -->
  <div class="card">
    <div class="section-title">Vehicle Breakdown · All Cameras</div>
    <div class="breakdown-grid" id="breakdown-grid">
      <!-- filled by JS -->
    </div>
  </div>

  <!-- Efficiency history chart -->
  <div class="card">
    <div class="section-title">Queue Reduction History</div>
    <div class="chart-wrap">
      <canvas id="eff-chart"></canvas>
    </div>
  </div>

</div>

<script>
// ── Socket.IO connection ──
const socket = io();

// ── Chart setup ──
const ctx = document.getElementById('eff-chart').getContext('2d');
const effChart = new Chart(ctx, {
  type: 'line',
  data: {
    labels: [],
    datasets: [{
      label: 'Queue Reduction %',
      data: [],
      borderColor: '#00e57a',
      backgroundColor: 'rgba(0,229,122,0.08)',
      borderWidth: 2,
      pointRadius: 3,
      pointBackgroundColor: '#00e57a',
      fill: true,
      tension: 0.35,
    }]
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { ticks: { color: '#6b8a82', font: { size: 10 } }, grid: { color: '#243330' } },
      y: {
        ticks: { color: '#6b8a82', font: { size: 10 } },
        grid: { color: '#243330' },
        min: 0, max: 100,
      }
    }
  }
});

// ── State ──
let totalCycles    = 0;
let effSum         = 0;
let maxGreenTime   = 45;   // updated from phase plan

// ── Countdown ring helpers ──
const CIRCUMFERENCE = 226.2;   // 2π × 36
let countdownMax = 45;

function setRing(value, max, state) {
  const ring  = document.getElementById('ring-fill');
  const ratio = Math.max(0, Math.min(1, value / max));
  ring.style.strokeDashoffset = CIRCUMFERENCE * (1 - ratio);
  const colors = { GREEN: '#00e57a', YELLOW: '#f5c842', ALL_RED: '#ff4f4f' };
  ring.style.stroke = colors[state] || '#00e57a';
}

// ── Signal box helpers ──
const CAM_IDS = ['camera_1', 'camera_2', 'camera_3', 'camera_4'];

function setSignals(currentGreen, phaseState, vehicleCounts) {
  CAM_IDS.forEach(cam => {
    const box   = document.getElementById('sig-' + cam);
    const count = document.getElementById('sig-count-' + cam);
    if (!box) return;

    const total = vehicleCounts?.[cam]?.total ?? 0;
    if (count) count.textContent = total;

    box.className = 'sig-box ';
    if (cam === currentGreen) {
      if (phaseState === 'YELLOW')  box.className += 'yellow-phase';
      else if (phaseState === 'ALL_RED') box.className += 'red-phase';
      else box.className += 'green-phase';
    } else {
      box.className += 'red-phase';
    }

    // position classes
    const positions = { camera_1: 'sig-north', camera_2: 'sig-east',
                        camera_3: 'sig-south',  camera_4: 'sig-west' };
    box.className += ' ' + (positions[cam] || '');
  });
}

// ── Phase table ──
function renderPhaseTable(phases, currentGreen) {
  const tbody = document.getElementById('phase-tbody');
  if (!phases || phases.length === 0) return;

  const maxPressure = Math.max(...phases.map(p => p.pressure));

  tbody.innerHTML = phases.map(p => {
    const isActive = p.camera === currentGreen;
    const pct = maxPressure > 0 ? (p.pressure / maxPressure * 100).toFixed(0) : 0;
    const greenPct = (p.green_time / 45 * 100).toFixed(0);
    const dirMap = { camera_1: 'North', camera_2: 'East',
                     camera_3: 'South', camera_4: 'West' };
    const dir = dirMap[p.camera] || p.camera;
    const badgeClass = isActive ? 'green' : 'red';
    const badgeLabel = isActive ? '▶ ACTIVE' : '◼ WAITING';

    return `<tr class="${isActive ? 'active-row' : ''}">
      <td><strong>${dir}</strong></td>
      <td style="font-family:var(--font-mono);color:var(--muted)">${p.pressure.toFixed(1)}</td>
      <td style="font-family:var(--font-mono);color:var(--green)">${p.green_time}s</td>
      <td style="font-family:var(--font-mono);color:var(--yellow)">${p.carryover.toFixed(0)}</td>
      <td class="bar-cell">
        <div class="bar-track">
          <div class="bar-fill" style="width:${greenPct}%"></div>
        </div>
      </td>
      <td><span class="badge ${badgeClass}">${badgeLabel}</span></td>
    </tr>`;
  }).join('');
}

// ── Vehicle breakdown ──
function renderBreakdown(vehicleCounts) {
  const grid = document.getElementById('breakdown-grid');
  if (!vehicleCounts) return;

  const dirMap = { camera_1: 'North', camera_2: 'East',
                   camera_3: 'South', camera_4: 'West' };
  const types  = ['car', 'motorcycle', 'truck', 'bus'];
  const icons  = { car: '🚗', motorcycle: '🏍', truck: '🚛', bus: '🚌' };

  grid.innerHTML = Object.entries(vehicleCounts).map(([cam, data]) => {
    const breakdown = data.breakdown || {};
    const rows = types.map(t => {
      const n = breakdown[t] || 0;
      if (n === 0) return '';
      return `<div class="type-row">
        <span><span class="type-dot dot-${t}"></span>${icons[t]} ${t}</span>
        <span class="type-count" style="color:var(--${t})">${n}</span>
      </div>`;
    }).join('');

    return `<div class="cam-box">
      <div class="cam-name">${dirMap[cam] || cam}
        <span style="color:var(--green);font-family:var(--font-mono);margin-left:6px">${data.total}</span>
      </div>
      ${rows || '<div style="font-size:0.72rem;color:var(--muted)">No vehicles</div>'}
    </div>`;
  }).join('');
}

// ── Main update handler ──
socket.on('state_update', function(data) {
  // Header
  document.getElementById('hdr-time').textContent =
    new Date(data.timestamp).toLocaleTimeString();
  document.getElementById('hdr-cycle').textContent = 'Cycle ' + data.cycle_number;

  // KPIs — queue_reduction_pct is the primary metric
  document.getElementById('kpi-efficiency').textContent =
    (data.queue_reduction_pct ?? data.efficiency_pct ?? 0).toFixed(1) + '%';
  document.getElementById('kpi-co2').textContent =
    (data.co2_saved_g ?? 0).toFixed(1);
  document.getElementById('kpi-fuel').textContent =
    (data.fuel_saved_ml ?? 0).toFixed(1);
  document.getElementById('kpi-phase').textContent =
    data.current_green || '—';
  document.getElementById('kpi-phase-state').textContent =
    (data.phase_state || '').replace('_', ' ');

  // Countdown ring
  const cstate = data.phase_state || 'GREEN';
  const cval   = data.countdown_s ?? 0;
  if (cstate === 'GREEN')  countdownMax = 45;
  if (cstate === 'YELLOW') countdownMax = 4;
  if (cstate === 'ALL_RED') countdownMax = 1;
  document.getElementById('countdown-num').textContent   = cval;
  document.getElementById('countdown-label').textContent = cstate.replace('_',' ');
  const ringColors = { GREEN: '#00e57a', YELLOW: '#f5c842', ALL_RED: '#ff4f4f' };
  document.getElementById('countdown-num').style.color   = ringColors[cstate] || '#00e57a';
  setRing(cval, countdownMax, cstate);

  // Signal boxes
  setSignals(data.current_green, data.phase_state, data.vehicle_counts);

  // Phase table
  renderPhaseTable(data.phase_plan, data.current_green);

  // Emission panel
  const cumCO2  = data.cumulative_co2_saved_g  ?? 0;
  const cumFuel = data.cumulative_fuel_saved_ml ?? 0;
  document.getElementById('em-co2-total').textContent  = cumCO2.toFixed(1);
  document.getElementById('em-fuel-total').textContent = cumFuel.toFixed(1) + ' mL';
  document.getElementById('em-co2-cycle').textContent  = (data.co2_saved_g  ?? 0).toFixed(1) + ' g';
  document.getElementById('em-fuel-cycle').textContent = (data.fuel_saved_ml ?? 0).toFixed(1) + ' mL';
  document.getElementById('em-cycles').textContent     = data.cycle_number ?? 0;

  // Avg efficiency accumulator
  totalCycles++;
  effSum += (data.efficiency_pct ?? 0);
  document.getElementById('em-avg-eff').textContent =
    (effSum / totalCycles).toFixed(1) + '%';

  // CO2 → km equivalent (avg car emits ~120 g CO2/km)
  document.getElementById('em-equiv').textContent =
    (cumCO2 / 120).toFixed(2);

  // Vehicle breakdown
  renderBreakdown(data.vehicle_counts);

  // Queue reduction chart — one point per cycle
  if (data.cycle_number && effChart.data.labels.indexOf('C' + data.cycle_number) === -1) {
    effChart.data.labels.push('C' + data.cycle_number);
    effChart.data.datasets[0].data.push(
      (data.queue_reduction_pct ?? data.efficiency_pct ?? 0).toFixed(1)
    );
    if (effChart.data.labels.length > 30) {
      effChart.data.labels.shift();
      effChart.data.datasets[0].data.shift();
    }
    effChart.update('none');
  }
});

socket.on('connect',    () => console.log('Dashboard connected'));
socket.on('disconnect', () => console.log('Dashboard disconnected'));
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Flask app factory
# ---------------------------------------------------------------------------
def create_app(dashboard_state: dict, state_lock: threading.Lock):
    app      = Flask(__name__)
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

    @app.route("/")
    def index():
        return render_template_string(DASHBOARD_HTML)

    @socketio.on("connect")
    def on_connect():
        logger.info("Browser connected to dashboard")
        # Push current state immediately on connect
        with state_lock:
            snapshot = dict(dashboard_state)
        if snapshot:
            emit("state_update", snapshot)

    # Background task: push state to all clients every second
    def push_loop():
        while True:
            time.sleep(1)
            with state_lock:
                snapshot = dict(dashboard_state)
            if snapshot:
                socketio.emit("state_update", snapshot)

    push_thread = threading.Thread(target=push_loop, daemon=True)
    push_thread.start()

    return app, socketio


# ---------------------------------------------------------------------------
# Standalone demo mode
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import math
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    state: dict           = {}
    lock: threading.Lock  = threading.Lock()

    app, socketio = create_app(state, lock)

    # Inject synthetic demo data so the dashboard looks live without running
    # the full simulation
    def _demo_loop():
        cycle = 0
        cameras = ["camera_1", "camera_2", "camera_3", "camera_4"]
        phases_order = ["camera_1", "camera_2", "camera_3", "camera_4"]
        phase_idx = 0
        countdown = 30

        while True:
            cam = phases_order[phase_idx % 4]
            if countdown <= 0:
                phase_idx += 1
                cycle += 1 if phase_idx % 4 == 0 else 0
                countdown = 30

            counts = {}
            for i, c in enumerate(cameras):
                base = 8 + 10 * abs(math.sin(cycle * 0.5 + i))
                counts[c] = {
                    "total":    int(base),
                    "weighted": round(base * 1.2, 1),
                    "breakdown": {"car": int(base * 0.7), "bus": max(1, int(base * 0.1)),
                                  "truck": max(0, int(base * 0.05)), "motorcycle": int(base * 0.15)},
                }

            with lock:
                state.update({
                    "timestamp":               datetime.now().isoformat(),
                    "cycle_number":            cycle + 1,
                    "current_green":           cam,
                    "phase_state":             "GREEN",
                    "countdown_s":             countdown,
                    "efficiency_pct":          72.0 + 10 * math.sin(cycle * 0.4),
                    "co2_saved_g":             round(14.0 + 5 * abs(math.sin(cycle)), 1),
                    "fuel_saved_ml":           round(6.0  + 2 * abs(math.sin(cycle)), 1),
                    "cumulative_co2_saved_g":  round((cycle + 1) * 14.0, 1),
                    "cumulative_fuel_saved_ml":round((cycle + 1) * 6.0, 1),
                    "vehicle_counts":          counts,
                    "phase_plan": [
                        {"camera": c, "green_time": 20 + i * 5,
                         "pressure": 30 - i * 5, "carryover": max(0, i * 2 - 1)}
                        for i, c in enumerate(cameras)
                    ],
                })
            countdown -= 1
            time.sleep(1)

    demo_thread = threading.Thread(target=_demo_loop, daemon=True)
    demo_thread.start()

    logger.info("Demo dashboard → http://127.0.0.1:5000")
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)