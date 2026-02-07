FROM nginx:alpine
COPY . /usr/share/nginx/html

# Optional: if you ever add a custom nginx config, you'd copy it here.
# COPY nginx.conf /etc/nginx/conf.d/default.conf
