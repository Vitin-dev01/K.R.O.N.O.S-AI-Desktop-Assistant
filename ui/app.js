// ==========================================================
// K.R.O.N.O.S // NÚCLEO HOLOGRÁFICO REATIVO A VOZ (60 FPS)
// ==========================================================
const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
let voiceAnalyser = null;
let voiceDataArray = null;
let audioEl = null;

function initAudioAnalyser() {
    if (voiceAnalyser) return;
    try {
        if (audioCtx.state === 'suspended') audioCtx.resume();
        audioEl = document.getElementById('kronos-audio-player');
        const source = audioCtx.createMediaElementSource(audioEl);
        voiceAnalyser = audioCtx.createAnalyser();
        voiceAnalyser.fftSize = 128;
        voiceAnalyser.smoothingTimeConstant = 0.75;
        const bufferLength = voiceAnalyser.frequencyBinCount;
        voiceDataArray = new Uint8Array(bufferLength);
        source.connect(voiceAnalyser);
        voiceAnalyser.connect(audioCtx.destination);
    } catch (e) {
        console.warn("Audio Analyser:", e);
    }
}

window.playVoiceAudio = function(base64Wav, finalState) {
    initAudioAnalyser();
    audioEl = document.getElementById('kronos-audio-player');
    audioEl.src = "data:audio/wav;base64," + base64Wav;

    audioEl.onplay = () => {
        isSpeaking = true;
        updateCoreState('SPEAKING');
    };

    audioEl.onended = () => {
        isSpeaking = false;
        updateCoreState(finalState || 'IDLE');

        autoListenTimer = setTimeout(() => {
            if (!isMicRecording && document.getElementById('tab-home').classList.contains('active')) {
                window.toggleMicrophone(true);
            }
        }, 1000);
    };

    audioEl.play().catch(e => console.warn(e));
};

window.setAudioElementVolume = function(volPercent) {
    const el = document.getElementById('kronos-audio-player');
    if (el) el.volume = Math.max(0, Math.min(1, volPercent / 100));
};

let isSpeaking = false;
let isMicRecording = false;
let autoListenTimer = null;

// Parâmetros configuráveis pelo usuário (Sliders)
let userSpeedMultiplier = 1.0;
let userBloomStrength = 1.6;

const container = document.getElementById('canvas-container');
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 0.1, 1000);

let camRadius = 8.0;
let camTheta = 0;
let camPhi = Math.PI / 2;

function updateCameraPosition() {
    camera.position.x = camRadius * Math.sin(camPhi) * Math.sin(camTheta);
    camera.position.y = camRadius * Math.cos(camPhi);
    camera.position.z = camRadius * Math.sin(camPhi) * Math.cos(camTheta);
    camera.lookAt(0, 0, 0);
}
updateCameraPosition();

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
container.appendChild(renderer.domElement);

const renderScene = new THREE.RenderPass(scene, camera);
const bloomPass = new THREE.UnrealBloomPass(
    new THREE.Vector2(window.innerWidth, window.innerHeight),
    userBloomStrength,
    0.4,
    0.18
);

const composer = new THREE.EffectComposer(renderer);
composer.addPass(renderScene);
composer.addPass(bloomPass);

const coreGroup = new THREE.Group();
scene.add(coreGroup);

const ambientLight = new THREE.AmbientLight(0xffffff, 0.4);
scene.add(ambientLight);

const heartLight = new THREE.PointLight(0xff9900, 2.5, 35);
coreGroup.add(heartLight);

// 1. Coração do Núcleo
const heartGeo = new THREE.SphereGeometry(0.38, 32, 32);
const heartMat = new THREE.MeshStandardMaterial({
    color: 0xffaa22,
    emissive: 0xff7700,
    emissiveIntensity: 1.4,
    roughness: 0.1,
    metalness: 0.5
});
const heartMesh = new THREE.Mesh(heartGeo, heartMat);
coreGroup.add(heartMesh);

// 2. Casca de Mini-Esferas 3D
const particleCount = 1200;
const sphereRadius = 1.65;
const miniSphereGeo = new THREE.SphereGeometry(0.026, 8, 8);
const miniSphereMat = new THREE.MeshStandardMaterial({
    color: 0xffcc44,
    emissive: 0xff8800,
    emissiveIntensity: 1.3,
    roughness: 0.2,
    metalness: 0.8
});

const instancedParticles = new THREE.InstancedMesh(miniSphereGeo, miniSphereMat, particleCount);
const dummy = new THREE.Object3D();

const goldenRatio = (1 + Math.sqrt(5)) / 2;
for (let i = 0; i < particleCount; i++) {
    const theta = 2 * Math.PI * i / goldenRatio;
    const phi = Math.acos(1 - 2 * (i + 0.5) / particleCount);

    const x = sphereRadius * Math.sin(phi) * Math.cos(theta);
    const y = sphereRadius * Math.sin(phi) * Math.sin(theta);
    const z = sphereRadius * Math.cos(phi);

    dummy.position.set(x, y, z);
    dummy.updateMatrix();
    instancedParticles.setMatrixAt(i, dummy.matrix);
}
instancedParticles.instanceMatrix.needsUpdate = true;
coreGroup.add(instancedParticles);

// 3. Poeira Estelar
function createRoundStarTexture() {
    const canvas = document.createElement('canvas');
    canvas.width = 64;
    canvas.height = 64;
    const ctx = canvas.getContext('2d');
    const grad = ctx.createRadialGradient(32, 32, 0, 32, 32, 30);
    grad.addColorStop(0, 'rgba(255, 255, 255, 1)');
    grad.addColorStop(0.3, 'rgba(255, 210, 110, 0.8)');
    grad.addColorStop(1, 'rgba(0, 0, 0, 0)');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(32, 32, 30, 0, Math.PI * 2);
    ctx.fill();
    return new THREE.CanvasTexture(canvas);
}

const spaceStarsCount = 650;
const starsGeo = new THREE.BufferGeometry();
const starsPos = new Float32Array(spaceStarsCount * 3);

for (let i = 0; i < spaceStarsCount; i++) {
    const r = 3.5 + Math.random() * 8.0;
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);

    starsPos[i * 3] = r * Math.sin(phi) * Math.cos(theta);
    starsPos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
    starsPos[i * 3 + 2] = r * Math.cos(phi);
}

starsGeo.setAttribute('position', new THREE.BufferAttribute(starsPos, 3));
const starsMat = new THREE.PointsMaterial({
    map: createRoundStarTexture(),
    color: 0xffd27d,
    size: 0.045,
    transparent: true,
    opacity: 0.7,
    depthWrite: false,
    blending: THREE.AdditiveBlending
});
const spaceStars = new THREE.Points(starsGeo, starsMat);
scene.add(spaceStars);

// 4. Anéis
function createShieldRing(rotX, rotY, rotZ, radius = 2.35) {
    const ringParent = new THREE.Group();
    ringParent.rotation.set(rotX, rotY, rotZ);

    const rGeo = new THREE.TorusGeometry(radius, 0.016, 16, 140);
    const rMat = new THREE.MeshStandardMaterial({
        color: 0xffaa33,
        emissive: 0xd47a20,
        emissiveIntensity: 1.1,
        roughness: 0.1,
        metalness: 0.9
    });
    const mainRing = new THREE.Mesh(rGeo, rMat);
    ringParent.add(mainRing);

    const subGeo = new THREE.TorusGeometry(radius * 0.97, 0.006, 8, 100);
    const subMat = new THREE.MeshBasicMaterial({ color: 0xffbb44, transparent: true, opacity: 0.4 });
    const subRing = new THREE.Mesh(subGeo, subMat);
    ringParent.add(subRing);

    const clampGeo = new THREE.BoxGeometry(0.08, 0.05, 0.07);
    const clampMat = new THREE.MeshStandardMaterial({ color: 0xffaa33, metalness: 0.9, roughness: 0.1 });

    for (let i = 0; i < 4; i++) {
        const angle = (Math.PI / 2) * i;
        const clamp = new THREE.Mesh(clampGeo, clampMat);
        clamp.position.x = Math.cos(angle) * radius;
        clamp.position.y = Math.sin(angle) * radius;
        clamp.rotation.z = angle;
        ringParent.add(clamp);
    }

    coreGroup.add(ringParent);
    return { group: ringParent, mat: rMat };
}

const ringXZ = createShieldRing(Math.PI / 2, 0, 0, 2.35);
const ringYZ = createShieldRing(0, Math.PI / 2, 0, 2.35);
const ringXY = createShieldRing(0, 0, 0, 2.35);

// Câmera Orbital 360°
let isDragging = false;
let prevMouse = { x: 0, y: 0 };

window.addEventListener('mousedown', (e) => {
    if (e.target.tagName !== 'INPUT' && e.target.tagName !== 'BUTTON' && !e.target.closest('.modal-overlay') && !e.target.closest('.mic-btn')) {
        isDragging = true;
        prevMouse = { x: e.clientX, y: e.clientY };
    }
});

window.addEventListener('mousemove', (e) => {
    if (isDragging) {
        const deltaX = e.clientX - prevMouse.x;
        const deltaY = e.clientY - prevMouse.y;

        camTheta -= deltaX * 0.006;
        camPhi -= deltaY * 0.006;
        camPhi = Math.max(0.08, Math.min(Math.PI - 0.08, camPhi));

        updateCameraPosition();
        prevMouse = { x: e.clientX, y: e.clientY };
    }
});

window.addEventListener('mouseup', () => isDragging = false);

window.addEventListener('wheel', (e) => {
    camRadius += e.deltaY * 0.004;
    camRadius = Math.max(4.0, Math.min(14.0, camRadius));
    updateCameraPosition();
});

// Loop de Animação com Controle Dinâmico dos Sliders
const clock = new THREE.Clock();

function animate() {
    requestAnimationFrame(animate);
    const time = clock.getElapsedTime();

    let realVoiceLevel = 0;
    if (isSpeaking && voiceAnalyser && voiceDataArray) {
        voiceAnalyser.getByteFrequencyData(voiceDataArray);
        let sum = 0;
        for (let i = 0; i < voiceDataArray.length; i++) {
            sum += voiceDataArray[i];
        }
        realVoiceLevel = (sum / voiceDataArray.length) / 255.0;
    }

    let pulse;
    if (isSpeaking) {
        pulse = 1.0 + realVoiceLevel * 0.45;
        heartLight.intensity = 2.5 + realVoiceLevel * 5.0;
        bloomPass.strength = userBloomStrength + realVoiceLevel * 1.5;
    } else if (isMicRecording) {
        pulse = 1.0 + Math.sin(time * 8.0) * 0.05;
        heartLight.intensity = 2.5;
        bloomPass.strength = userBloomStrength;
    } else {
        pulse = 1.0 + Math.sin(time * 2.2) * 0.03;
        heartLight.intensity = 2.5;
        bloomPass.strength = userBloomStrength; // RESPEITA O SLIDER DO USUÁRIO!
    }
    heartMesh.scale.set(pulse, pulse, pulse);

    // ROTAÇÃO RESPEITA O SLIDER DO USUÁRIO!
    instancedParticles.rotation.y = time * ((isSpeaking ? 0.25 : 0.12) * userSpeedMultiplier);
    spaceStars.rotation.y = time * (0.015 * userSpeedMultiplier);

    composer.render();
}
animate();

window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
    composer.setSize(window.innerWidth, window.innerHeight);
    updateCameraPosition();
});

// Cores dos Estados
function updateCoreState(state) {
    const badge = document.getElementById('status-badge');
    if (!badge) return;
    const dot = badge.querySelector('.status-dot');
    const label = badge.querySelector('.status-label');
    label.innerText = `KRONOS // STATUS: ${state}`;

    let colorHex = 0xffaa33;
    let emissiveHex = 0xff7700;
    let accentCss = '#e59438';

    switch (state) {
        case 'LISTENING':
            colorHex = 0xffd700;
            emissiveHex = 0xffb700;
            accentCss = '#ffd700';
            break;
        case 'SPEAKING':
            colorHex = 0xffc400;
            emissiveHex = 0xff9900;
            accentCss = '#ffc400';
            break;
        case 'THINKING':
            colorHex = 0xffffff;
            emissiveHex = 0xeeeeee;
            accentCss = '#ffffff';
            break;
        case 'BRAVO':
            colorHex = 0xff1133;
            emissiveHex = 0xff0022;
            accentCss = '#ff1133';
            break;
        case 'EXECUTING':
            colorHex = 0xcd7f32;
            emissiveHex = 0xb86820;
            accentCss = '#cd7f32';
            break;
        case 'ERROR':
            colorHex = 0x8b0000;
            emissiveHex = 0x660000;
            accentCss = '#8b0000';
            break;
        default:
            colorHex = 0xffaa33;
            emissiveHex = 0xff7700;
            accentCss = '#e59438';
            break;
    }

    heartMat.color.setHex(colorHex);
    heartMat.emissive.setHex(emissiveHex);
    heartLight.color.setHex(emissiveHex);

    miniSphereMat.color.setHex(colorHex);
    miniSphereMat.emissive.setHex(emissiveHex);

    ringXZ.mat.color.setHex(colorHex);
    ringXZ.mat.emissive.setHex(emissiveHex);
    ringYZ.mat.color.setHex(colorHex);
    ringYZ.mat.emissive.setHex(emissiveHex);
    ringXY.mat.color.setHex(colorHex);
    ringXY.mat.emissive.setHex(emissiveHex);

    dot.style.backgroundColor = accentCss;
    dot.style.boxShadow = `0 0 10px ${accentCss}`;
    badge.style.borderColor = `${accentCss}44`;
    label.style.color = accentCss;
}

// Microfone
let silenceTimeout = null;

window.toggleMicrophone = async function(isAuto = false) {
    const micBtn = document.getElementById('btn-mic');
    const input = document.getElementById('command-input');

    if (!isMicRecording) {
        isMicRecording = true;
        micBtn.classList.add('recording');
        updateCoreState('LISTENING');
        input.placeholder = isAuto ? "Ouvindo sua resposta... (Fale agora)" : "Ouvindo sua voz... (Fale e clique para enviar)";

        if (window.pywebview && window.pywebview.api) {
            await window.pywebview.api.start_manual_recording();
        }

        if (isAuto) {
            silenceTimeout = setTimeout(() => {
                if (isMicRecording) window.toggleMicrophone(false);
            }, 5500);
        }

    } else {
        if (silenceTimeout) clearTimeout(silenceTimeout);
        isMicRecording = false;
        micBtn.classList.remove('recording');
        updateCoreState('THINKING');
        input.placeholder = "Processando ordem...";

        if (window.pywebview && window.pywebview.api) {
            const text = await window.pywebview.api.stop_manual_recording();
            // Silêncio: restaura IDLE imediatamente!
            if (!text || !text.trim()) {
                updateCoreState('IDLE');
                input.placeholder = "Transmitir ordem ao núcleo... (ou clique no mic)";
            }
        }
    }
};

// ==========================================================
// ATALHOS DE TECLADO: F11 (TELA CHEIA) E CTRL+ESPAÇO
// ==========================================================
window.addEventListener('keydown', (e) => {
    if (e.key === 'F11') {
        e.preventDefault();
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.toggle_fullscreen();
        }
    }
    if (e.ctrlKey && e.code === 'Space') {
        e.preventDefault();
        window.toggleMicrophone();
    }
});

// Navegação entre Janelas
window.switchTab = function(tabName) {
    document.querySelectorAll('.dock-item').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.modal-overlay').forEach(m => m.classList.add('hidden'));

    const btn = document.getElementById(`tab-${tabName}`);
    if (btn) btn.classList.add('active');

    if (window.telemetryInterval) {
        clearInterval(window.telemetryInterval);
        window.telemetryInterval = null;
    }

    if (tabName !== 'home') {
        const modal = document.getElementById(`modal-${tabName}`);
        if (modal) modal.classList.remove('hidden');

        if (tabName === 'graficos') {
            if (typeof initCharts === 'function' && !window.lineChart) initCharts();
            if (typeof updateTelemetryData === 'function') {
                updateTelemetryData();
                window.telemetryInterval = setInterval(updateTelemetryData, 1200);
            }
        }
    }
};

// Gráficos Chart.js
window.lineChart = null;
window.barChart = null;
window.radarChart = null;
window.telemetryInterval = null;

const timeLabels = Array.from({ length: 20 }, (_, i) => `${20 - i}s`);
const cpuHistory = Array(20).fill(0);
const ramHistory = Array(20).fill(0);

function initCharts() {
    const elLine = document.getElementById('lineChart');
    if (!elLine) return;
    const ctxLine = elLine.getContext('2d');
    window.lineChart = new Chart(ctxLine, {
        type: 'line',
        data: {
            labels: timeLabels,
            datasets: [
                {
                    label: 'CPU (%)',
                    data: cpuHistory,
                    borderColor: '#ffaa40',
                    backgroundColor: 'rgba(255, 170, 64, 0.15)',
                    fill: true,
                    tension: 0.35,
                    borderWidth: 2,
                    pointRadius: 0
                },
                {
                    label: 'RAM (%)',
                    data: ramHistory,
                    borderColor: '#ffffff',
                    backgroundColor: 'rgba(255, 255, 255, 0.12)',
                    fill: true,
                    tension: 0.35,
                    borderWidth: 2,
                    pointRadius: 0
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            scales: {
                y: { min: 0, max: 100, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#8c98ad', font: { family: 'Orbitron', size: 9 } } },
                x: { grid: { display: false }, ticks: { color: '#8c98ad', font: { family: 'Orbitron', size: 9 } } }
            },
            plugins: { legend: { display: false } }
        }
    });

    const elBar = document.getElementById('barChart');
    if (!elBar) return;
    const ctxBar = elBar.getContext('2d');
    window.barChart = new Chart(ctxBar, {
        type: 'bar',
        data: {
            labels: ['CPU', 'RAM', 'DISCO', 'UP (KB)', 'DOWN (KB)'],
            datasets: [{
                data: [0, 0, 0, 0, 0],
                backgroundColor: [
                    'rgba(255, 170, 64, 0.85)',
                    'rgba(255, 255, 255, 0.85)',
                    'rgba(205, 127, 50, 0.85)',
                    'rgba(184, 104, 32, 0.8)',
                    'rgba(229, 148, 56, 0.8)'
                ],
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 400 },
            scales: {
                y: { min: 0, max: 100, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#8c98ad', font: { family: 'Orbitron', size: 9 } } },
                x: { grid: { display: false }, ticks: { color: '#e2e8f0', font: { family: 'Orbitron', size: 9 } } }
            },
            plugins: { legend: { display: false } }
        }
    });

    const elRadar = document.getElementById('radarChart');
    if (!elRadar) return;
    const ctxRadar = elRadar.getContext('2d');
    window.radarChart = new Chart(ctxRadar, {
        type: 'radar',
        data: {
            labels: ['PROCESSAMENTO', 'MEMÓRIA', 'DISCO C:', 'VELOCIDADE', 'ESTABILIDADE'],
            datasets: [{
                label: 'Carga Operacional',
                data: [20, 20, 20, 20, 95],
                backgroundColor: 'rgba(212, 122, 32, 0.25)',
                borderColor: '#ffaa40',
                borderWidth: 2,
                pointBackgroundColor: '#ffffff',
                pointBorderColor: '#ffaa40',
                pointRadius: 3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 400 },
            scales: {
                r: {
                    min: 0,
                    max: 100,
                    angleLines: { color: 'rgba(255,255,255,0.08)' },
                    grid: { color: 'rgba(255,255,255,0.06)' },
                    pointLabels: { color: '#cbd5e1', font: { family: 'Orbitron', size: 9 } },
                    ticks: { display: false }
                }
            },
            plugins: { legend: { display: false } }
        }
    });
}

async function updateTelemetryData() {
    if (!window.pywebview || !window.pywebview.api) return;

    try {
        const data = await window.pywebview.api.get_telemetry();

        const cpuLbl = document.getElementById('lbl-cpu-val');
        const ramLbl = document.getElementById('lbl-ram-val');
        if (cpuLbl) cpuLbl.innerText = `${data.cpu_percent}%`;
        if (ramLbl) ramLbl.innerText = `${data.ram_percent}%`;

        cpuHistory.shift();
        cpuHistory.push(data.cpu_percent);
        ramHistory.shift();
        ramHistory.push(data.ram_percent);

        if (window.lineChart) {
            window.lineChart.data.datasets[0].data = cpuHistory;
            window.lineChart.data.datasets[1].data = ramHistory;
            window.lineChart.update();
        }

        if (window.barChart) {
            barChart.data.datasets[0].data = [
                data.cpu_percent,
                data.ram_percent,
                data.disk_percent,
                Math.min(100, data.cpu_percent * 0.8),
                Math.min(100, data.ram_percent * 0.9)
            ];
            barChart.update();
        }

        if (window.radarChart) {
            const estabilidade = Math.max(10, 100 - (data.cpu_percent * 0.5 + data.ram_percent * 0.5));
            radarChart.data.datasets[0].data = [
                data.cpu_percent,
                data.ram_percent,
                data.disk_percent,
                data.cpu_percent,
                estabilidade
            ];
            radarChart.update();
        }
    } catch (err) {
        console.error("Erro telemetria:", err);
    }
}

// ==========================================================
// CONTROLES DE SLIDERS CORRIGIDOS (FUNCIONAM NA HORA!)
// ==========================================================
const sSpeed = document.getElementById('slider-speed');
if (sSpeed) {
    sSpeed.addEventListener('input', (e) => {
        userSpeedMultiplier = parseFloat(e.target.value); // CORREÇÃO: APLICA À VARIÁVEL DE ROTAÇÃO!
        document.getElementById('lbl-speed').innerText = `${userSpeedMultiplier.toFixed(1)}x`;
    });
}

const sScale = document.getElementById('slider-scale');
if (sScale) {
    sScale.addEventListener('input', (e) => {
        const s = parseFloat(e.target.value);
        coreGroup.scale.set(s, s, s);
        document.getElementById('lbl-scale').innerText = `${s.toFixed(1)}x`;
    });
}

const sGlow = document.getElementById('slider-glow');
if (sGlow) {
    sGlow.addEventListener('input', (e) => {
        userBloomStrength = parseFloat(e.target.value); // CORREÇÃO: APLICA À VARIÁVEL DO BLOOM!
        bloomPass.strength = userBloomStrength;
        document.getElementById('lbl-glow').innerText = userBloomStrength.toFixed(2);
    });
}

const sVoiceVol = document.getElementById('slider-voice-vol');
if (sVoiceVol) {
    sVoiceVol.addEventListener('input', (e) => {
        const v = parseInt(e.target.value);
        document.getElementById('lbl-voice-vol').innerText = `${v}%`;
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.set_voice_volume(v);
        }
    });
}

window.changeMode = async function(modeName) {
    document.querySelectorAll('.mode-select-btn').forEach(btn => btn.classList.remove('active'));
    const targetBtn = document.getElementById(`btn-mode-${modeName.toLowerCase()}`);
    if (targetBtn) targetBtn.classList.add('active');

    if (window.pywebview && window.pywebview.api) {
        const res = await window.pywebview.api.set_mode(modeName);
        appendActionLog(`[SISTEMA]: ${res}`, 'user-msg');
    }
};

// Envio por Teclado
async function sendCommand() {
    const input = document.getElementById('command-input');
    if (!input) return;
    const text = input.value.trim();
    if (!text) return;

    input.value = '';
    updateCoreState('THINKING');

    appendActionLog(`VOCÊ: ${text}`, 'user-msg');

    if (window.pywebview && window.pywebview.api) {
        try {
            const res = await window.pywebview.api.process_user_message(text);
            if (res.pending) {
                setCommandProcessing(true);
            } else if (res.busy) {
                appendActionLog(`KRONOS: ${res.fala}`, 'error-msg');
            } else {
                window.completeUserMessage(res);
            }
        } catch (err) {
            setCommandProcessing(false);
            updateCoreState('ERROR');
            appendActionLog(`ERRO TÉCNICO: ${String(err)}`, 'error-msg');
        }
    }
}

window.completeUserMessage = function(result) {
    setCommandProcessing(false);
    const state = result.estado || 'IDLE';
    if (result.pensamento) appendThoughtLog(result.pensamento);
    const logType = state === 'BRAVO' ? 'error-msg' : 'kronos-msg';
    appendActionLog(`KRONOS: ${result.fala || 'Ordem concluída.'}`, logType);
    updateCoreState(state);
};

function setCommandProcessing(processing) {
    const cancelButton = document.getElementById('btn-cancel-command');
    if (cancelButton) {
        cancelButton.hidden = !processing;
        cancelButton.disabled = !processing;
        cancelButton.textContent = 'Cancelar tarefa';
    }
}

window.cancelCurrentCommand = async function() {
    const cancelButton = document.getElementById('btn-cancel-command');
    if (!cancelButton || !window.pywebview || !window.pywebview.api) return;
    cancelButton.disabled = true;
    cancelButton.textContent = 'Cancelando...';
    try {
        const result = await window.pywebview.api.cancel_current_command();
        appendActionLog(`SISTEMA: ${result}`, 'user-msg');
    } catch (err) {
        cancelButton.disabled = false;
        cancelButton.textContent = 'Cancelar tarefa';
        appendActionLog(`ERRO AO CANCELAR: ${String(err)}`, 'error-msg');
    }
};

const cmdInp = document.getElementById('command-input');
if (cmdInp) {
    cmdInp.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') sendCommand();
    });
}

// Logs
function appendThoughtLog(thought) {
    const feed = document.getElementById('thought-feed');
    if (!feed) return;
    const msg = document.createElement('div');
    msg.className = 'thought-msg';
    const time = new Date().toLocaleTimeString();
    msg.innerHTML = `<span class="time-stamp">[${time}]</span><span class="thought-txt">💭 ${thought}</span>`;
    feed.appendChild(msg);
    feed.scrollTop = feed.scrollHeight;
}

function appendActionLog(action, extraClass = '') {
    const feed = document.getElementById('action-feed');
    if (!feed) return;
    const msg = document.createElement('div');
    msg.className = `action-msg ${extraClass}`;
    const time = new Date().toLocaleTimeString();
    msg.innerHTML = `<span class="time-stamp">[${time}]</span><span class="action-txt">${action}</span>`;
    feed.appendChild(msg);
    feed.scrollTop = feed.scrollHeight;
}

window.clearAllLogs = function() {
    const tFeed = document.getElementById('thought-feed');
    const aFeed = document.getElementById('action-feed');
    if (tFeed) {
        tFeed.innerHTML = `
            <div class="thought-msg">
                <span class="time-stamp">[SISTEMA]</span>
                <span class="thought-txt">Fluxo de consciência reinicializado.</span>
            </div>`;
    }
    if (aFeed) {
        aFeed.innerHTML = `
            <div class="action-msg">
                <span class="time-stamp">[SISTEMA]</span>
                <span class="action-txt">Registros operacionais arquivados. Novo ciclo iniciado.</span>
            </div>`;
    }
    showToast("REGISTROS LIMPOS COM SUCESSO");
};

window.exportAuditLogs = async function() {
    if (!window.pywebview || !window.pywebview.api) return;

    let fullText = "=====================================================\n";
    fullText += "       K.R.O.N.O.S // RELATÓRIO OFICIAL DE AUDITORIA\n";
    fullText += `       DATA: ${new Date().toLocaleString()}\n`;
    fullText += "=====================================================\n\n";

    fullText += "--- [FLUXO DE CONSCIÊNCIA / MENTE PRÓPRIA] ---\n";
    document.querySelectorAll('#thought-feed .thought-msg').forEach(el => {
        fullText += el.innerText.trim() + "\n";
    });

    fullText += "\n--- [REGISTRO OPERACIONAL / AUDITORIA] ---\n";
    document.querySelectorAll('#action-feed .action-msg').forEach(el => {
        fullText += el.innerText.trim() + "\n";
    });

    fullText += "\n=====================================================\n";
    fullText += "FIM DO RELATÓRIO // K.R.O.N.O.S OPERATIONAL CORE\n";

    const feedback = await window.pywebview.api.export_logs(fullText);
    showToast(feedback.toUpperCase());
};

function showToast(msg) {
    const toast = document.getElementById('export-feedback');
    if (toast) {
        toast.innerText = msg;
        toast.style.opacity = '1';
        setTimeout(() => { toast.style.opacity = '0'; }, 3000);
    }
}