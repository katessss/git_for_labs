#include <iostream>
#include  <filesystem> 
#include <fstream> 
#include <string> 
#include <unordered_map> 
#include <iomanip> 
# include <sstream> 
using namespace std;

// Алгоритм FNV-1a 
string compute_file_hash(const filesystem::path& filepath) {
    ifstream f(filepath, ios::binary);
    if (!f.is_open()) {
        throw runtime_error("Не удалось открыть файл");
    }

    uint64_t hash = 0xcbf29ce484222325; 
    uint64_t prime = 0x1099511628211;
    char buffer[4096];
    while (f.good()) { 
        f.read(buffer, sizeof(buffer)); 
        int bytes_read = f.gcount(); 
        for (int i = 0; i < bytes_read; ++i) { 
            hash ^= static_cast<uint8_t>(buffer[i]);
            hash *= prime;
        }
    }

    stringstream  res;
    res << hex << setw(16) << setfill('0') << hash;
    return res.str();
}


int main(int argc, char* argv[]) {
    setlocale(LC_ALL, "");

    filesystem::path target_dir = argv[1]; 
   
    if (!filesystem::exists(target_dir) || !filesystem::is_directory(target_dir)) {
        cerr << "Ошибка: Указанный путь не существует или не является директорией." << endl;
        return 1;
    }

    unordered_map<string, filesystem::path> seen_hashes;
    
    int files_processed = 0;
    int duplicates_found = 0;

    cout << "Сканирование директории: " << filesystem::absolute(target_dir) << " ...\n" << endl;

    for (const auto& obj : filesystem::recursive_directory_iterator(target_dir)) {
        if (!obj.is_regular_file() || obj.is_symlink()) {
            continue;
        }

        filesystem::path current_path = obj.path();
        files_processed++;

        try {
            string hash = compute_file_hash(current_path);
            auto it = seen_hashes.find(hash);

            if (it == seen_hashes.end()) {
                seen_hashes[hash] = current_path;
            } else {
                filesystem::path original_path = it->second; 
                if (filesystem::equivalent(current_path, original_path)) { 
                    continue;
                }
                
                cout << "Дубликат " << current_path.filename() << " == " << original_path.filename() << endl;
                filesystem::remove(current_path);                
                filesystem::create_hard_link(original_path, current_path);
        
                duplicates_found++;
            }
        } catch (const exception& ex) {
            cerr << "Ошибка при обработке файла " << current_path << ": " << ex.what() << endl;
        }
    }

    cout << "\nВсего файлов проверено: " << files_processed << endl;
    cout << "Дубликатов заменено:" << duplicates_found << endl;

    return 0;
}