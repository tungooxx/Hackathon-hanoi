import maylanh from '../assets/prod/maylanh.jpg'
import quatdieuhoa from '../assets/prod/quatdieuhoa.jpg'
import tivi from '../assets/prod/tivi.jpg'
import maylocnuoc from '../assets/prod/maylocnuoc.jpg'
import tudong from '../assets/prod/tudong.jpg'
import quat from '../assets/prod/quat.jpg'
import loa from '../assets/prod/loa.jpg'
import maylockhongkhi from '../assets/prod/maylockhongkhi.jpg'
import tulanh from '../assets/prod/tulanh.jpg'
import maygiat from '../assets/prod/maygiat.jpg'
import giadung from '../assets/prod/giadung.jpg'
import maysayquanao from '../assets/prod/maysayquanao.jpg'
import robot from '../assets/prod/robot.jpg'
import noicom from '../assets/prod/noicom.jpg'
import massage from '../assets/prod/massage.jpg'

export const navCategories = [
  'máy lạnh giá tốt',
  'tủ lạnh',
  'quạt điều hòa',
  'máy sấy quần áo',
  'smart tivi',
  'máy lọc nước',
  'bồn nước',
  'máy lọc không khí',
  'quạt mát',
  'tủ đông',
]

export const quickCategories = [
  { label: 'Máy lạnh', img: maylanh, badge: '5.190k', badgeType: 'price' },
  { label: 'Quạt điều hòa', img: quatdieuhoa, badge: '4.190k', badgeType: 'price' },
  { label: 'Tivi', img: tivi, badge: '3.590k', badgeType: 'price' },
  { label: 'Máy lọc nước', img: maylocnuoc, badge: null },
  { label: 'Tủ đông mát', img: tudong, badge: '3.590k', badgeType: 'price' },
  { label: 'Quạt', img: quat, badge: null },
  { label: 'Loa', img: loa, badge: null },
  { label: 'Máy lọc không khí', img: maylockhongkhi, badge: null },
  { label: 'Tủ lạnh', img: tulanh, badge: 'HOT', badgeType: 'hot' },
  { label: 'Máy giặt', img: maygiat, badge: '2.990k', badgeType: 'price' },
  { label: 'Gia dụng', img: giadung, badge: '-50%', badgeType: 'discount' },
  { label: 'Máy sấy quần áo', img: maysayquanao, badge: '4.990k', badgeType: 'price' },
  { label: 'Robot hút bụi', img: robot, badge: null },
  { label: 'Nồi cơm điện', img: noicom, badge: null },
  { label: 'Sức khỏe & làm đẹp', img: massage, badge: null },
  { label: 'Tất cả danh mục', img: null, badge: null, isAll: true },
]

export const promoTabs = [
  { label: 'FLASH SALE', highlight: true },
  { label: 'GIẢM ĐẾN 50%+' },
  { label: 'TIVI WORLD CUP' },
  { label: 'TỦ ĐÔNG MÁT GIẢM SÂU' },
  { label: 'Máy lạnh' },
  { label: 'Máy giặt' },
  { label: 'Nồi cơm' },
  { label: 'Máy sấy' },
  { label: 'Loa' },
  { label: 'Quạt điều hoà' },
]

export const flashSaleSlots = [
  { time: 'Đang diễn ra', countdown: '02:59:49', active: true },
  { time: 'Sắp diễn ra', label: '21:30' },
  { time: 'Ngày mai', label: '00:00' },
  { time: 'Ngày mai', label: '09:00' },
  { time: 'Ngày mai', label: '12:00' },
]

export const flashSaleProducts = [
  { name: 'Máy lạnh World Cup', tag: 'Bỏ nhỏ lấy Tivi 0đ', img: maylanh },
  { name: 'Tivi World Cup', tag: 'Bỏ nhỏ lấy Tivi 0đ', img: tivi },
  { name: 'Máy giặt Toshiba', tag: '', img: maygiat },
  { name: 'Máy lạnh Inverter', tag: '', img: maylanh },
  { name: 'Tivi World Cup', tag: 'Bỏ nhỏ lấy Tivi 0đ', img: tivi },
  { name: 'Máy xay Sunhouse', tag: '4 cánh, thép không gỉ', img: giadung },
]

export const carouselSlides = [
  new URL('../assets/slide-1.png', import.meta.url).href,
  new URL('../assets/slide-2.png', import.meta.url).href,
  new URL('../assets/slide-3.png', import.meta.url).href,
  new URL('../assets/slide-4.png', import.meta.url).href,
  new URL('../assets/slide-5.png', import.meta.url).href,
  new URL('../assets/slide-6.png', import.meta.url).href,
  new URL('../assets/slide-7.png', import.meta.url).href,
]
