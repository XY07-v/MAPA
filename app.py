import os
import json
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify, session, redirect
from pymongo import MongoClient

app = Flask(__name__)
app.secret_key = "nestle_bi_fixed_2026"

# --- CONEXIÓN MONGODB ---
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://ANDRES_VANEGAS:CF32fUhOhrj70dY5@cluster0.dtureen.mongodb.net/?appName=Cluster0")
client = MongoClient(MONGO_URI)
db = client['NestleDB']
puntos_col = db['puntos_venta']

# --- INTERFAZ HTML PRINCIPAL ---
HTML_LAYOUT = """
<!DOCTYPE html>
<html>
<head>
    <title>Visor Georreferencial - Nestlé BI</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    
    <style>
        html, body, #map {
            width: 100%;
            height: 100%;
            margin: 0;
            padding: 0;
        }
        /* Panel de búsquedas */
        #search-container {
            position: absolute;
            top: 15px;
            left: 55px;
            z-index: 1000;
            background: rgba(255, 255, 255, 0.95);
            padding: 15px;
            border-radius: 10px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            width: 290px;
        }
        #search-container h4 {
            margin: 0 0 10px 0;
            color: #333;
            font-size: 16px;
            border-bottom: 2px solid #007bff;
            padding-bottom: 5px;
        }
        #search-container input {
            width: 100%;
            margin-bottom: 10px;
            padding: 8px;
            box-sizing: border-box;
            border: 1px solid #ccc;
            border-radius: 5px;
            font-size: 13px;
        }
        #search-buttons-layout {
            display: flex;
            gap: 5px;
        }
        .btn-control {
            flex: 1;
            padding: 9px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-weight: bold;
            font-size: 13px;
            transition: background 0.3s;
        }
        #btn-buscar { background-color: #007bff; color: white; }
        #btn-buscar:hover { background-color: #0056b3; }
        #btn-restablecer { background-color: #6c757d; color: white; }
        #btn-restablecer:hover { background-color: #5a6268; }
        
        /* Burbuja flotante */
        #info-burbuja {
            position: absolute;
            bottom: 35px;
            right: 25px;
            z-index: 1000;
            background: rgba(33, 37, 41, 0.9);
            color: white;
            padding: 15px;
            border-radius: 12px;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            box-shadow: 0 4px 20px rgba(0,0,0,0.4);
            display: none;
            max-width: 280px;
            border-left: 5px solid #ff4d4d;
        }
    </style>
</head>
<body>

<div id="search-container">
    <h4>Buscador Inteligente</h4>
    <input type="text" id="input-pdv" placeholder="Nombre del Punto de Venta (POC)...">
    <input type="text" id="input-bmb" placeholder="Código BMB...">
    <div id="search-buttons-layout">
        <button id="btn-buscar" class="btn-control" onclick="buscarPuntoEnBD()">Buscar</button>
        <button id="btn-restablecer" class="btn-control" onclick="restablecerMapa()">Ver Todos</button>
    </div>
</div>

<div id="info-burbuja">
    <h4 style="margin:0 0 6px 0; color:#ff4d4d; font-size:15px;">Métrica de Distancia</h4>
    <p id="distancia-texto" style="margin:0; font-size:13px; line-height:1.4;">Calculando trayecto...</p>
</div>

<div id="map"></div>

<script>
    let mapObject = L.map('map').setView([4.60971, -74.08175], 12);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors'
    }).addTo(mapObject);

    let miUbicacion = null;
    let marcadorUsuario = null;
    let marcadorDestino = null;
    let rutaPolilinea = null;

    // 1. Obtener Geolocalización del Dispositivo
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(function(position) {
            miUbicacion = {
                lat: position.coords.latitude,
                lng: position.coords.longitude
            };
            
            marcadorUsuario = L.marker([miUbicacion.lat, miUbicacion.lng], {
                icon: L.icon({
                    iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png',
                    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
                    iconSize: [25, 41],
                    iconAnchor: [12, 41],
                    popupAnchor: [1, -34],
                    shadowSize: [41, 41]
                })
            }).addTo(mapObject).bindPopup("<b>Tu ubicación real</b>").openPopup();
            
        }, function(error) {
            console.error("Geolocalización denegada:", error.message);
        });
    }

    // Fórmula Haversine
    function calcularDistancia(lat1, lon1, lat2, lon2) {
        const R = 6371; 
        const dLat = (lat2 - lat1) * Math.PI / 180;
        const dLon = (lon2 - lon1) * Math.PI / 180;
        const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
                  Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon/2) * Math.sin(dLon/2);
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
        return (R * c).toFixed(2);
    }

    // 2. Buscar en el Backend de Flask e interactuar con MongoDB
    function buscarPuntoEnBD() {
        const pdv = document.getElementById('input-pdv').value;
        const bmb = document.getElementById('input-bmb').value;

        if (!pdv && !bmb) {
            alert("Escribe un criterio de búsqueda.");
            return;
        }

        // Limpiar elementos anteriores si existen
        if (marcadorDestino) { mapObject.removeLayer(marcadorDestino); }
        if (rutaPolilinea) { mapObject.removeLayer(rutaPolilinea); }

        // Petición asíncrona a la API de Flask
        fetch(`/api/buscar?pdv=${encodeURIComponent(pdv)}&bmb=${encodeURIComponent(bmb)}`)
            .then(res => res.json())
            .then(data => {
                if (data.status === "error") {
                    alert(data.message);
                    return;
                }

                const destLat = data.lat;
                const destLng = data.lng;

                // Crear Marcador del Punto de Venta encontrado
                marcadorDestino = L.marker([destLat, destLng]).addTo(mapObject);
                
                let contentHtml = `
                    <b>Punto de Venta:</b> ${data.pdv}<br>
                    <b>BMB:</b> ${data.bmb}<br>
                    <b>Ciudad:</b> ${data.ciudad}
                `;
                marcadorDestino.bindPopup(contentHtml).openPopup();

                // Trazar Línea Roja e Intersección limpia
                if (miUbicacion) {
                    const coordenadas = [
                        [miUbicacion.lat, miUbicacion.lng],
                        [destLat, destLng]
                    ];
                    rutaPolilinea = L.polyline(coordenadas, {
                        color: 'red',
                        weight: 4,
                        opacity: 0.8,
                        dashArray: '5, 10'
                    }).addTo(mapObject);

                    const bounds = L.latLngBounds([miUbicacion, [destLat, destLng]]);
                    mapObject.fitBounds(bounds, { padding: [50, 50] });

                    // Mostrar Burbuja con distancia real calculada
                    const km = calcularDistancia(miUbicacion.lat, miUbicacion.lng, destLat, destLng);
                    document.getElementById('info-burbuja').style.display = 'block';
                    document.getElementById('distancia-texto').innerHTML = `<b>POC:</b> ${data.pdv}<br><b>Distancia:</b> <span style="color:#ff4d4d; font-weight:bold;">${km} km</span>`;
                } else {
                    mapObject.setView([destLat, destLng], 16);
                }
            })
            .catch(err => console.error("Error en Fetch:", err));
    }

    function restablecerMapa() {
        document.getElementById('input-pdv').value = "";
        document.getElementById('input-bmb').value = "";
        document.getElementById('info-burbuja').style.display = 'none';
        if (marcadorDestino) { mapObject.removeLayer(marcadorDestino); }
        if (rutaPolilinea) { mapObject.removeLayer(rutaPolilinea); }
        mapObject.setView([4.60971, -74.08175], 12);
    }
</script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_LAYOUT)

# --- ENDPOINT API DE BÚSQUEDA ---
@app.route('/api/buscar')
def buscar_punto():
    query_pdv = request.args.get('pdv', '').strip()
    query_bmb = request.args.get('bmb', '').strip()
    
    filtro = {}
    
    # Búsqueda por Regex flexible (No importa mayúsculas/minúsculas ni nombres exactos)
    if query_pdv:
        filtro['Punro de venta'] = {'$regex': query_pdv, '$options': 'i'}
    if query_bmb:
        filtro['BMB'] = {'$regex': query_bmb, '$options': 'i'}
        
    registro = puntos_col.find_one(filtro)
    
    if not registro:
        return jsonify({"status": "error", "message": "Punto de venta no encontrado en la base de datos."})
    
    try:
        # Tratamiento y parseo seguro del campo 'Ruta' (coordenadas)
        coordenadas = registro['Ruta'].split(',')
        lat = float(coordenadas[0].strip())
        lng = float(coordenadas[1].strip())
    except Exception:
        return jsonify({"status": "error", "message": "El registro existe pero sus coordenadas en 'Ruta' son inválidas."})

    return jsonify({
        "status": "success",
        "pdv": registro.get('Punro de venta', 'N/A'),
        "bmb": registro.get('BMB', 'N/A'),
        "ciudad": registro.get('Ciudad', 'N/A'),
        "lat": lat,
        "lng": lng
    })

if __name__ == '__main__':
    # Ejecución local controlada
    app.run(debug=True, port=5000)
