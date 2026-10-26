# Despliegue en Ubuntu

Este proyecto es una app Flask. En produccion no debe ejecutarse con
`python3 run.py` expuesto a internet. Usa Gunicorn como servidor WSGI interno
y Nginx como proxy publico.

## 1. Instalar dependencias

```bash
cd ~/Desktop/ONEBoard
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
```

## 2. Configurar `.env`

Para servir detras de Nginx, deja la app escuchando solo en localhost:

```env
HOST=127.0.0.1
PORT=5001
FLASK_DEBUG=0
SECRET_KEY=cambia-esto-por-una-clave-larga-y-privada
GOOGLE_REDIRECT_URI=https://tu-dominio.com/integrations/google-search-console/callback
```

Si usas Google OAuth, registra ese mismo redirect URI HTTPS en Google Cloud.

## 3. Probar Gunicorn

```bash
source env/bin/activate
gunicorn --bind 127.0.0.1:5001 app:app
```

En otra terminal:

```bash
curl -I http://127.0.0.1:5001
```

No pruebes el backend con `https://127.0.0.1:5001`. Ese puerto habla HTTP
interno. Si un cliente manda HTTPS ahi, Flask/Gunicorn mostrara errores como
`Bad request syntax ('\x16\x03...')`.

## 4. Servicio systemd

Crea `/etc/systemd/system/oneboard.service`:

```ini
[Unit]
Description=ONEBoard Gunicorn
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/Desktop/ONEBoard
EnvironmentFile=/home/ubuntu/Desktop/ONEBoard/.env
ExecStart=/home/ubuntu/Desktop/ONEBoard/env/bin/gunicorn --workers 3 --bind 127.0.0.1:5001 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

Activa el servicio:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now oneboard
sudo systemctl status oneboard
```

## 5. Nginx

Crea `/etc/nginx/sites-available/oneboard`:

```nginx
server {
    listen 80;
    server_name tu-dominio.com;

    location / {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Activalo:

```bash
sudo ln -s /etc/nginx/sites-available/oneboard /etc/nginx/sites-enabled/oneboard
sudo nginx -t
sudo systemctl reload nginx
```

## 6. HTTPS

Instala Certbot y deja que configure el certificado:

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d tu-dominio.com
```

Despues de esto, entra por:

```text
https://tu-dominio.com
```

No abras `https://tu-dominio.com:5001` ni `https://IP_DEL_SERVIDOR:5001`.
El puerto `5001` queda privado para Nginx.
