FROM alpine
WORKDIR /app

RUN apk add --no-cache python3 py3-lxml py3-pip readline poppler-utils curl
RUN pip3 install requests-cache cssselect click
