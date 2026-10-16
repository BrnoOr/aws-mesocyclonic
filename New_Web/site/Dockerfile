# Imagen del sitio de Vórtice: nginx sirve site/page.html (con la consola) en / y pasa /api/ a la API
# de inferencia (ver nginx.conf). page.html es un fragmento HTML; aquí se envuelve en un documento.
FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY assets /usr/share/nginx/html/assets
COPY page.html /tmp/page.html
RUN { printf '<!doctype html>\n<html lang="es">\n<head>\n<meta charset="utf-8">\n'; \
      printf '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'; \
      printf '</head>\n<body>\n'; cat /tmp/page.html; printf '\n</body>\n</html>\n'; } \
      > /usr/share/nginx/html/index.html \
 && rm /tmp/page.html

EXPOSE 80
HEALTHCHECK CMD wget -qO- http://localhost/health || exit 1
