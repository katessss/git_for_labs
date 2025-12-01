#include <iostream>           
#include <thread>
#include <mutex> 
#include <condition_variable>
#include <chrono> 
using namespace std;

struct EventData {
    int id;
    string payload;

    EventData(int i, string s) : id(i), payload(s) {}
};


class Monitor {
private:
    mutex mtx;                     
    condition_variable cv_produced; 
    condition_variable cv_consumed; 
    EventData* data = nullptr;          
    bool ready = false;         

    public:
    void push(EventData* newData) { 
        unique_lock<mutex> lock(mtx);
        cv_consumed.wait(lock, [this]() { return !ready; }); 
        
        data = newData;  
        ready = true;    
        
        cout << "[Поставщик]  -> Событие отправлено..." << endl;
        lock.unlock(); 
        cv_produced.notify_one();
    }



    EventData* pop() {
        unique_lock<mutex> lock(mtx);
        cv_produced.wait(lock, [this]() { return ready; });
        
        EventData* receivedData = data; 
        ready = false;
        data = nullptr;

        cout << "[Потребитель] <- Событие получено..." << endl;
        lock.unlock();
        cv_consumed.notify_one();
        return receivedData; 
    }
};


Monitor monitor;

void producer() {
    for (int i = 1; i <= 5; ++i) { 
        this_thread::sleep_for(chrono::seconds(1));
        EventData* event = new EventData(i, "SomethingHeavy");
        monitor.push(event);
    }
}


void consumer() {
    for (int i = 1; i <= 5; ++i) { 
        EventData* event = monitor.pop();        
        delete event;
    }
}



int main() {
    setlocale(LC_ALL, "Russian");
    cout << "Запуск монитора..." << endl;

    thread t1(producer);
    thread t2(consumer); 

    t1.join(); 
    t2.join();
    return 0;
}