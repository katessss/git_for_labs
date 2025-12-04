#include <iostream>   
#include <vector>     
#include <algorithm>  
#include <cstring>
#include <csignal> 
#include <unistd.h> 
#include <sys/types.h> 
#include <sys/socket.h> 
#include <sys/select.h> 
#include <netinet/in.h>
#include <fcntl.h> 
#include <errno.h>
using namespace std;

const int PORT = 1984; 
volatile int wasSigHup = 0;

void sigHupHandler(int r) {
    wasSigHup = 1;
}   

int main() {
    int listenSocket = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP); 
    if (listenSocket < 0) { 
        perror("socket");
        return 1;
    }   
    int opt = 1;
    setsockopt(listenSocket, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in addr; 
    addr.sin_family = AF_INET; 
    addr.sin_port = htons(PORT); 
    addr.sin_addr.s_addr = INADDR_ANY; 
        
    if (bind(listenSocket, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("bind");
        return 1;
    }

    if (listen(listenSocket, 1) < 0) {
        perror("listen");
        return 1;
    }

    cout << "Сервер запущен на порту " << PORT << ". PID: " << getpid() << endl;
    cout << "Для проверки сигнала выполните: kill -HUP " << getpid() << endl;

    sigset_t blockedMask, origMask;
    sigemptyset(&blockedMask);
    sigaddset(&blockedMask, SIGHUP);
    // Блокировка сигнала
    sigprocmask(SIG_BLOCK, &blockedMask, &origMask); 

    // обработчик
    struct sigaction sa; 
    memset(&sa, 0, sizeof(sa)); 
    sa.sa_handler = sigHupHandler;
    sa.sa_flags = 0; 
    sigaction(SIGHUP, &sa, NULL);  
    int clientSock = -1;

    while (true) {
        fd_set readfds;
        FD_ZERO(&readfds);

        FD_SET(listenSocket, &readfds); 
        int maxFd = listenSocket; 

        if (clientSock != -1) { 
            FD_SET(clientSock, &readfds);

            if (clientSock > maxFd) {
                maxFd = clientSock; 
            }
        }

        int ready = pselect(maxFd + 1, &readfds, NULL, NULL, NULL, &origMask);

        if (ready == -1) {  
            if (errno == EINTR) {   
                
                if (wasSigHup) {
                    cout << "[SIGNAL] Получен сигнал SIGHUP!" << endl;
                    wasSigHup = 0; 
                } 
                continue;
            } else {
                perror("pselect");
                break;
            }
        }

        if (wasSigHup) {
            cout << "[SIGNAL] Получен сигнал SIGHUP (смешанный)!" << endl;
            wasSigHup = 0;
        }

        if (FD_ISSET(listenSocket, &readfds)) { 
            int newSock = accept(listenSocket, NULL, NULL);
            if (newSock >= 0) { 
                if (clientSock == -1) {
                    clientSock = newSock;
                    cout << "[NET] Новое соединение принято (Socket " << newSock << ")" << endl;
                } else {
                    cout << "[NET] Клиент занят, соединение отклонено" << endl;
                    close(newSock);
                }
            } else {
                perror("accept");
            }

        }

        if (clientSock != -1 && FD_ISSET(clientSock, &readfds)) { 
            char buffer[1024];
            int bytesRead = read(clientSock, buffer, sizeof(buffer));

            if (bytesRead > 0) {
                cout << "[DATA] Получено байт: " << bytesRead << endl;
            } else {
                cout << "[NET] Клиент отключился" << endl;
                close(clientSock);
                clientSock = -1; 
            }
        }
    }

    if (clientSock != -1) close(clientSock);
    close(listenSocket);
    return 0;
}