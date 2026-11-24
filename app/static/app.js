// AEGIS Mission Control Client-Side Logic

// Dynamically resolve API Base (supports both unified Render hosting and decoupled Vercel Edge frontend)
const API_BASE = window.location.hostname.includes("vercel.app")
    ? "https://aegis-self-healing-platform.onrender.com"
    : "";

let activeIncidentsCount = 0;
let lastKnownMem = 0;
let startTime = Date.now();

// --- Format helpers ---
function formatUptime(seconds) {
    const hrs = Math.floor(seconds / 3600).toString().padStart(2, '0');
    const mins = Math.floor((seconds % 3600) / 60).toString().padStart(2, '0');
    const secs = Math.floor(seconds % 60).toString().padStart(2, '0');
    return `${hrs}:${mins}:${secs}`;
}

function getTimeString() {
    const now = new Date();
    return now.toTimeString().split(' ')[0];
}

// --- Add event to SRE Timeline ---
function addTimelineEvent(tag, tagClass, text) {
    const timeline = document.getElementById('timeline-list');
    const item = document.createElement('div');
    item.className = 'timeline-item';
    item.innerHTML = `
        <div class="time-marker mono">${getTimeString()}</div>
        <div class="time-content">
            <span class="tag ${tagClass}">${tag}</span>
            <p>${text}</p>
        </div>
    `;
    timeline.insertBefore(item, timeline.firstChild);
}

// --- Fetch live telemetry ---
async function fetchTelemetry() {
    try {
        const res = await fetch(`${API_BASE}/api/status`);
        if (!res.ok) throw new Error('Unhealthy status returned');
        const data = await res.json();

        // Update indicators
        document.getElementById('hostname-display').innerText = `node // ${data.hostname}`;
        document.getElementById('uptime-display').innerText = formatUptime(data.uptime_seconds);

        // Memory
        document.getElementById('mem-val').innerText = data.memory_mb;
        const memPercent = Math.min(100, Math.round((data.memory_mb / 500) * 100));
        document.getElementById('mem-meter').style.width = `${memPercent}%`;

        // CPU
        document.getElementById('cpu-val').innerText = data.cpu_percent.toFixed(1);
        document.getElementById('cpu-meter').style.width = `${Math.min(100, data.cpu_percent)}%`;

        // Health Status
        const healthEl = document.getElementById('health-val');
        const probeEl = document.getElementById('probe-status');
        const clusterIndicator = document.getElementById('cluster-indicator');

        if (data.chaos_state.is_healthy && data.chaos_state.is_ready && !data.chaos_state.simulated_errors) {
            healthEl.innerText = "HEALTHY";
            healthEl.className = "kpi-val text-green";
            probeEl.innerText = "PASSING";
            probeEl.className = "text-green";
            clusterIndicator.className = "dot pulse-green";
        } else {
            healthEl.innerText = "DEGRADED";
            healthEl.className = "kpi-val text-crimson";
            probeEl.innerText = "FAILING";
            probeEl.className = "text-crimson";
            clusterIndicator.className = "dot";
            clusterIndicator.style.backgroundColor = "var(--crimson)";
        }

        // Active incidents counter
        let activeCount = 0;
        if (!data.chaos_state.is_healthy) activeCount++;
        if (!data.chaos_state.is_ready) activeCount++;
        if (data.chaos_state.cpu_stress_active) activeCount++;
        if (data.chaos_state.artificial_latency_sec > 0) activeCount++;
        if (data.chaos_state.memory_leak_mb > 0) activeCount++;
        if (data.chaos_state.simulated_errors) activeCount++;

        document.getElementById('incident-counter').innerText = `${activeCount} ACTIVE INCIDENTS`;
        if (activeCount > 0) {
            document.getElementById('incident-counter').style.background = 'rgba(255, 51, 102, 0.2)';
            document.getElementById('incident-counter').style.color = 'var(--crimson)';
        } else {
            document.getElementById('incident-counter').style.background = 'rgba(255, 255, 255, 0.05)';
            document.getElementById('incident-counter').style.color = 'var(--text-secondary)';
        }

    } catch (err) {
        document.getElementById('health-val').innerText = "OFFLINE";
        document.getElementById('health-val').className = "kpi-val text-crimson";
        document.getElementById('probe-status').innerText = "DISCONNECTED";
        document.getElementById('probe-status').className = "text-crimson";
    }
}

// --- Chaos actions ---
async function triggerChaos(type) {
    let url = '';
    let eventTag = 'CHAOS';
    let eventClass = 'tag-alert';
    let eventMsg = '';

    switch(type) {
        case 'oom':
            url = '/chaos/oom?megabytes=120';
            eventMsg = 'Injected synthetic memory hog (+120MB). Simulating OOMKill pressure.';
            break;
        case 'crash':
            url = '/chaos/crash';
            eventMsg = 'Injected SIGKILL / exit(1). Simulating container CrashLoopBackOff.';
            break;
        case 'cpu':
            url = '/chaos/cpu?duration_sec=15';
            eventMsg = 'Injected CPU mathematical burn loop (15s). Simulating HPA spike.';
            break;
        case 'latency':
            url = '/chaos/latency?seconds=2.5';
            eventMsg = 'Injected 2.5s artificial latency on all requests. SLO breached.';
            break;
        case 'errors':
            url = '/chaos/errors?enable=true';
            eventMsg = 'Injected HTTP 500 error cascade on business routes.';
            break;
        case 'reset':
            url = '/chaos/reset';
            eventTag = 'HEALED';
            eventClass = 'tag-ok';
            eventMsg = 'Reset all injected chaos flags. System restored to baseline.';
            break;
    }

    addTimelineEvent(eventTag, eventClass, eventMsg);

    try {
        const res = await fetch(`${API_BASE}${url}`, { method: 'POST' });
        await res.json();
    } catch (err) {
        console.error('Chaos execution error:', err);
    }
}

// --- AIOps Post-Mortem Generator (Demo Simulation) ---
function generateAIMockReport() {
    const output = document.getElementById('aiops-content');
    output.innerHTML = `
        <div style="color: var(--violet); font-weight: 700; margin-bottom: 8px;">
            ✦ AIOps Autonomous Incident Analysis [DEMO SIMULATION]
        </div>
        <p><strong>Incident Archetype:</strong> Memory Pressure / Pod Crash Loop</p>
        <p><strong>Correlated Signals:</strong> <code>aegis_process_memory_usage_mb &gt; 380MB</code>, <code>http_request_duration_seconds p99 &gt; 2.2s</code></p>
        <p><strong>Autonomous Action Executed:</strong> AEGIS Remediation Bot intercepted Alertmanager webhook, verified circuit breaker, and patched Deployment resource limits (+25% buffer).</p>
        <p><strong>Mean Time to Recovery (MTTR):</strong> <span class="mono text-cyan" style="font-weight:700;">21.4 seconds</span> (Status verified: <code>/healthz HTTP 200 OK</code>)</p>
        <pre class="mono">
# Recommendation generated by AEGIS Intelligence:
1. Promote memory limit from 256Mi to 320Mi in k8s/base/app-deployment.yaml
2. Ingress rate-limiting configured at 250 req/sec to prevent memory ballooning
3. Circuit-breaker limit: 3 restarts / 10 mins (Safety status: Nominal)
        </pre>
    `;
    addTimelineEvent('AIOPS', 'tag-ai', 'AIOps generated root-cause diagnostic report & updated mitigation recommendations.');
}

// Track seen incident IDs to avoid duplicate timeline events
const seenIncidentIds = new Set();

// Start polling live incident stream from controller
async function fetchIncidents() {
    try {
        const res = await fetch(`${API_BASE}/api/incidents`);
        if (!res.ok) return;
        const incidents = await res.json();
        if (incidents && incidents.length > 0) {
            const latest = incidents[incidents.length - 1];
            
            // Update live MTTR display
            const mttrEl = document.getElementById('mttr-val');
            if (mttrEl && typeof latest.mttr_seconds === 'number') {
                mttrEl.innerText = latest.mttr_seconds.toFixed(1);
            }

            // Stream new incidents into timeline
            incidents.forEach(inc => {
                if (inc.incident_id && !seenIncidentIds.has(inc.incident_id)) {
                    seenIncidentIds.add(inc.incident_id);
                    addTimelineEvent('ALERT', 'tag-alert', `Alertmanager fired ${inc.alert_name || 'incident'} on ${inc.resource || 'workload'}.`);
                    addTimelineEvent('REMEDIATION', 'tag-healing', `AEGIS Controller executed ${inc.remediation_action || 'remediation'} (MTTR: ${inc.mttr_seconds || 0}s).`);
                }
            });

            const output = document.getElementById('aiops-content');
            if (output && !output.innerHTML.includes(latest.incident_id)) {
                output.innerHTML = `
                    <div style="color: var(--violet); font-weight: 700; margin-bottom: 8px;">
                        ✧ Live AIOps Incident Analysis [${latest.incident_id}]
                    </div>
                    <p><strong>Alert Triggered:</strong> <code>${latest.alert_name}</code></p>
                    <p><strong>Resource:</strong> <code>${latest.resource}</code></p>
                    <p><strong>Remediation Action:</strong> <code>${latest.remediation_action}</code></p>
                    <p><strong>MTTR:</strong> <span class="mono text-cyan" style="font-weight:700;">${latest.mttr_seconds}s</span></p>
                `;
            }
        }
    } catch (e) {}
}

setInterval(fetchTelemetry, 1500);
fetchTelemetry();
setInterval(fetchIncidents, 3000);
fetchIncidents();
