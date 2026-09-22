from confluent_kafka import Consumer, KafkaException, OFFSET_BEGINNING
import time
import os
import sys

KAFKA_HOST = os.environ.get('KAFKA_HOST')
KAFKA_TOPIC = os.environ.get('KAFKA_TOPIC')
KAFKA_GROUP = os.environ.get('KAFKA_GROUP') 
WORKER_ID = os.environ.get('HOSTNAME')

def main():
    print(f"Worker {WORKER_ID} (Group: {KAFKA_GROUP}) waiting for tasks...")
    
    conf = {
        'bootstrap.servers': KAFKA_HOST,
        'group.id': KAFKA_GROUP,          
        'auto.offset.reset': 'earliest', 
        'enable.auto.commit': True 
    }

    consumer = Consumer(conf)    
    consumer.subscribe([KAFKA_TOPIC])

    while True:
        try:
            msg = consumer.poll(1.0)
            
            if msg is None:
                continue
            
            if msg.error():
                print(f"Consumer error: {msg.error()}")
                continue

            item = msg.value().decode('utf-8') 
            print(f" [x] Worker {WORKER_ID} получил (from partition {msg.partition()}): {item}")
            
            time.sleep(len(item) * 10) # Имитация бурной деятельности
            
            print(f" [v] Worker {WORKER_ID} закончил: {item}")

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Unhandled exception: {e}")
            break

    consumer.close()

if __name__ == '__main__':
    try:
        main()
    except Exception:
        sys.exit(0)