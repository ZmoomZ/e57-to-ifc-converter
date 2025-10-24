import open3d as o3d
import numpy as np
import pye57
import json
import os
from typing import Dict, List, Tuple, Any

class PointCloudProcessor:
    """
    Класс для обработки облаков точек E57
    """
    
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.e57_path = f"uploads/{task_id}.e57"
        self.point_cloud = None
        self.downsampled_cloud = None
        
    def load_e57(self) -> bool:
        """
        Загрузка E57 файла
        """
        try:
            print(f"Загрузка файла: {self.e57_path}")
            
            # Читаем E57
            e57 = pye57.E57(self.e57_path)
            
            # Получаем данные первого скана
            data = e57.read_scan(0, colors=False, ignore_missing_fields=True)
            
            # Извлекаем координаты
            points = np.column_stack((data['cartesianX'], 
                                     data['cartesianY'], 
                                     data['cartesianZ']))
            
            # Создаем облако точек Open3D
            self.point_cloud = o3d.geometry.PointCloud()
            self.point_cloud.points = o3d.utility.Vector3dVector(points)
            
            print(f"Загружено точек: {len(points)}")
            return True
            
        except Exception as e:
            print(f"Ошибка загрузки E57: {e}")
            return False
    
    def filter_noise(self):
        """
        Фильтрация шумов
        """
        print("Фильтрация шумов...")
        
        # Statistical outlier removal
        cl, ind = self.point_cloud.remove_statistical_outlier(
            nb_neighbors=20,
            std_ratio=2.0
        )
        self.point_cloud = self.point_cloud.select_by_index(ind)
        
        print(f"После фильтрации: {len(self.point_cloud.points)} точек")
    
    def downsample(self, voxel_size: float = 0.05):
        """
        Уменьшение количества точек (downsampling)
        voxel_size: размер вокселя в метрах (0.05м = 5см)
        """
        print(f"Downsampling с voxel_size={voxel_size}...")
        
        self.downsampled_cloud = self.point_cloud.voxel_down_sample(voxel_size)
        
        print(f"После downsampling: {len(self.downsampled_cloud.points)} точек")
        
    def save_processed_cloud(self):
        """
        Сохранение обработанного облака в формате PLY
        """
        output_path = f"processed/{self.task_id}.ply"
        o3d.io.write_point_cloud(output_path, self.downsampled_cloud)
        print(f"Облако сохранено: {output_path}")
        return output_path


def process_point_cloud(task_id: str) -> Dict[str, Any]:
    """
    Главная функция обработки облака точек
    """
    try:
        processor = PointCloudProcessor(task_id)
        
        # 1. Загрузка E57
        if not processor.load_e57():
            return {"status": "error", "message": "Ошибка загрузки E57"}
        
        # 2. Фильтрация шумов
        processor.filter_noise()
        
        # 3. Downsampling
        processor.downsample(voxel_size=0.05)
        
        # 4. Сохранение
        ply_path = processor.save_processed_cloud()
        
        # TODO: Следующие шаги
        # 5. Сегментация (slabs, walls, columns)
        # 6. Создание IFC
        
        return {
            "status": "processed",
            "message": "Обработка завершена",
            "point_count": len(processor.downsampled_cloud.points),
            "ply_path": ply_path
        }
        
    except Exception as e:
        print(f"Ошибка обработки: {e}")
        return {"status": "error", "message": str(e)}