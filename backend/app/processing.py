import open3d as o3d
import numpy as np
import pye57
import json
import os
from typing import Dict, List, Tuple, Any

def detect_slabs(point_cloud: o3d.geometry.PointCloud, z_step: float = 0.05) -> List[Dict[str, Any]]:
    """
    Определение горизонтальных плит через анализ гистограммы высот
    Основано на методе из Cloud2BIM
    """
    print("Определение плит (slabs)...")
    
    points = np.asarray(point_cloud.points)
    z_coords = points[:, 2]  # Z координаты
    
    # Создаем гистограмму по высоте
    z_min, z_max = z_coords.min(), z_coords.max()
    bins = int((z_max - z_min) / z_step)
    hist, bin_edges = np.histogram(z_coords, bins=bins)
    
    # Находим пики в гистограмме (потенциальные плиты)
    threshold = np.max(hist) * 0.3  # 30% от максимума
    slab_candidates = []
    
    for i in range(len(hist)):
        if hist[i] > threshold:
            z_level = (bin_edges[i] + bin_edges[i+1]) / 2
            slab_candidates.append({
                'z': z_level,
                'density': hist[i]
            })
    
    # Группируем близкие пики (в пределах 0.3м считаем одной плитой)
    slabs = []
    if len(slab_candidates) > 0:
        current_slab = [slab_candidates[0]]
        
        for candidate in slab_candidates[1:]:
            if candidate['z'] - current_slab[-1]['z'] < 0.3:
                current_slab.append(candidate)
            else:
                # Завершаем текущую плиту
                avg_z = np.mean([s['z'] for s in current_slab])
                slabs.append({
                    'type': 'IfcSlab',
                    'z': float(avg_z),
                    'thickness': 0.3  # Стандартная толщина для MVP
                })
                current_slab = [candidate]
        
        # Добавляем последнюю плиту
        if len(current_slab) > 0:
            avg_z = np.mean([s['z'] for s in current_slab])
            slabs.append({
                'type': 'IfcSlab',
                'z': float(avg_z),
                'thickness': 0.3
            })
    
    print(f"Найдено плит: {len(slabs)}")
    return slabs

def detect_walls(point_cloud: o3d.geometry.PointCloud, grid_size: float = 0.1) -> List[Dict[str, Any]]:
    """
    Определение вертикальных стен через 2D гистограмму
    Упрощенная версия метода из Cloud2BIM
    """
    print("Определение стен (walls)...")
    
    points = np.asarray(point_cloud.points)
    
    # Берем только точки в средней части по высоте (90-100% высоты этажа)
    z_coords = points[:, 2]
    z_min, z_max = z_coords.min(), z_coords.max()
    z_range = z_max - z_min
    z_threshold = z_min + z_range * 0.5  # Берем верхние 50%
    
    wall_points = points[z_coords > z_threshold]
    
    if len(wall_points) == 0:
        return []
    
    # Проекция на плоскость XY
    xy_points = wall_points[:, :2]
    
    # Создаем 2D гистограмму
    x_min, x_max = xy_points[:, 0].min(), xy_points[:, 0].max()
    y_min, y_max = xy_points[:, 1].min(), xy_points[:, 1].max()
    
    x_bins = int((x_max - x_min) / grid_size) + 1
    y_bins = int((y_max - y_min) / grid_size) + 1
    
    hist_2d, x_edges, y_edges = np.histogram2d(
        xy_points[:, 0], 
        xy_points[:, 1], 
        bins=[x_bins, y_bins]
    )
    
    # Находим области с высокой плотностью (стены)
    threshold = np.max(hist_2d) * 0.2  # 20% от максимума
    wall_mask = hist_2d > threshold
    
    # Простое определение стен (для MVP)
    walls = []
    wall_height = z_max - z_min
    
    # Ищем вертикальные линии (стены вдоль X)
    for j in range(y_bins):
        wall_segments = []
        for i in range(x_bins):
            if wall_mask[i, j]:
                x_center = (x_edges[i] + x_edges[i+1]) / 2
                y_center = (y_edges[j] + y_edges[j+1]) / 2
                wall_segments.append([x_center, y_center])
        
        if len(wall_segments) > 5:  # Минимум 5 точек для стены
            segments_array = np.array(wall_segments)
            walls.append({
                'type': 'IfcWall',
                'start': [float(segments_array[0, 0]), float(segments_array[0, 1]), float(z_min)],
                'end': [float(segments_array[-1, 0]), float(segments_array[-1, 1]), float(z_min)],
                'height': float(wall_height),
                'thickness': 0.2  # Стандартная толщина 20см
            })
    
    # Ищем горизонтальные линии (стены вдоль Y)
    for i in range(x_bins):
        wall_segments = []
        for j in range(y_bins):
            if wall_mask[i, j]:
                x_center = (x_edges[i] + x_edges[i+1]) / 2
                y_center = (y_edges[j] + y_edges[j+1]) / 2
                wall_segments.append([x_center, y_center])
        
        if len(wall_segments) > 5:
            segments_array = np.array(wall_segments)
            walls.append({
                'type': 'IfcWall',
                'start': [float(segments_array[0, 0]), float(segments_array[0, 1]), float(z_min)],
                'end': [float(segments_array[-1, 0]), float(segments_array[-1, 1]), float(z_min)],
                'height': float(wall_height),
                'thickness': 0.2
            })
    
    print(f"Найдено стен: {len(walls)}")
    return walls

def detect_columns(point_cloud: o3d.geometry.PointCloud, grid_size: float = 0.5) -> List[Dict[str, Any]]:
    """
    Упрощенное определение колонн через 2D гистограмму (без DBSCAN)
    Для MVP - быстрый метод без больших затрат памяти
    """
    print("Определение колонн (columns)...")
    
    points = np.asarray(point_cloud.points)
    
    z_coords = points[:, 2]
    z_min, z_max = z_coords.min(), z_coords.max()
    height_range = z_max - z_min
    
    # Если высота меньше 2м, колонн нет
    if height_range < 2.0:
        print("Высота помещения слишком мала для определения колонн")
        return []
    
    # Используем 2D гистограмму на XY плоскости
    xy_points = points[:, :2]
    
    x_min, x_max = xy_points[:, 0].min(), xy_points[:, 0].max()
    y_min, y_max = xy_points[:, 1].min(), xy_points[:, 1].max()
    
    x_bins = int((x_max - x_min) / grid_size) + 1
    y_bins = int((y_max - y_min) / grid_size) + 1
    
    # Ограничиваем размер гистограммы
    x_bins = min(x_bins, 200)
    y_bins = min(y_bins, 200)
    
    hist_2d, x_edges, y_edges = np.histogram2d(
        xy_points[:, 0], 
        xy_points[:, 1], 
        bins=[x_bins, y_bins]
    )
    
    # Находим локальные максимумы (потенциальные колонны)
    threshold = np.max(hist_2d) * 0.6  # 60% от максимума
    
    columns = []
    
    for i in range(1, x_bins - 1):
        for j in range(1, y_bins - 1):
            # Проверяем, что это локальный максимум
            if hist_2d[i, j] > threshold:
                # Проверяем соседние клетки
                neighbors = hist_2d[i-1:i+2, j-1:j+2]
                if hist_2d[i, j] == np.max(neighbors):
                    x_center = (x_edges[i] + x_edges[i+1]) / 2
                    y_center = (y_edges[j] + y_edges[j+1]) / 2
                    
                    columns.append({
                        'type': 'IfcColumn',
                        'position': [float(x_center), float(y_center), float(z_min)],
                        'height': float(height_range),
                        'width': 0.4,  # Стандартная ширина 40см
                        'depth': 0.4
                    })
    
    # Ограничиваем количество колонн (для MVP)
    if len(columns) > 50:
        print(f"Найдено слишком много колонн ({len(columns)}), ограничиваем до 20")
        columns = columns[:20]
    
    print(f"Найдено колонн: {len(columns)}")
    return columns
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
    def segment_building_elements(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Сегментация элементов здания
        """
        print("\n=== Начало сегментации ===")
        
        # Используем downsampled облако для сегментации
        cloud = self.downsampled_cloud
        
        # 1. Определяем плиты
        slabs = detect_slabs(cloud)
        
        # 2. Определяем стены
        walls = detect_walls(cloud)
        
        # 3. Определяем колонны
        columns = detect_columns(cloud)
        
        return {
            'slabs': slabs,
            'walls': walls,
            'columns': columns
        }
    
    def save_model_data(self, elements: Dict[str, List[Dict[str, Any]]]):
        """
        Сохранение данных модели в JSON
        """
        model_data = {
            'task_id': self.task_id,
            'point_count': len(self.downsampled_cloud.points),
            'ply_path': f"processed/{self.task_id}.ply",
            'elements': elements,
            'bounds': {
                'min': list(self.downsampled_cloud.get_min_bound()),
                'max': list(self.downsampled_cloud.get_max_bound())
            }
        }
        
        output_path = f"models/{self.task_id}.json"
        with open(output_path, 'w') as f:
            json.dump(model_data, f, indent=2)
        
        print(f"Модель сохранена: {output_path}")
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
        
        # 4. Сохранение облака
        ply_path = processor.save_processed_cloud()
        
        # 5. Сегментация элементов
        elements = processor.segment_building_elements()
        
        # 6. Сохранение данных модели
        model_path = processor.save_model_data(elements)
        
        # 7. Генерация IFC файла
        from app.ifc_generator import generate_ifc
        ifc_path = generate_ifc(task_id)
        
        return {
            "status": "processed",
            "message": "Обработка завершена",
            "point_count": len(processor.downsampled_cloud.points),
            "ply_path": ply_path,
            "model_path": model_path,
            "ifc_path": ifc_path,
            "elements_count": {
                "slabs": len(elements['slabs']),
                "walls": len(elements['walls']),
                "columns": len(elements['columns'])
            }
        }
        
    except Exception as e:
        print(f"Ошибка обработки: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}