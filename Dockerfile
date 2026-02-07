with:
  context: .
  file: docker/Dockerfile
  push: true
  tags: ${{ secrets.DOCKERHUB_USERNAME }}/YOUR_REPO_NAME:latest
