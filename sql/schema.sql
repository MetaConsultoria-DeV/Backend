-- MySQL dump 10.13  Distrib 8.0.44, for Linux (x86_64)
--
-- Host: banco_de_dados_bd    Database: banco_de_dados
-- ------------------------------------------------------
-- Server version	9.7.0

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;
SET @MYSQLDUMP_TEMP_LOG_BIN = @@SESSION.SQL_LOG_BIN;
SET @@SESSION.SQL_LOG_BIN= 0;

--
-- GTID state at the beginning of the backup 
--

SET @@GLOBAL.GTID_PURGED=/*!80000 '+'*/ 'aa8ef542-34f0-11f1-897d-02420a0b001d:1-138';

--
-- Table structure for table `acomp_impedimento`
--

DROP TABLE IF EXISTS `acomp_impedimento`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `acomp_impedimento` (
  `id` int NOT NULL AUTO_INCREMENT,
  `acompanhamento_id` int NOT NULL,
  `houve_impedimentos` tinyint NOT NULL DEFAULT '0',
  `tipo_impedimento` varchar(100) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_impedit_acomp` (`acompanhamento_id`),
  CONSTRAINT `fk_impedit_acomp` FOREIGN KEY (`acompanhamento_id`) REFERENCES `acompanhamento_projeto` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `acomp_impedimento`
--

LOCK TABLES `acomp_impedimento` WRITE;
/*!40000 ALTER TABLE `acomp_impedimento` DISABLE KEYS */;
/*!40000 ALTER TABLE `acomp_impedimento` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `acomp_orientador`
--

DROP TABLE IF EXISTS `acomp_orientador`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `acomp_orientador` (
  `id` int NOT NULL AUTO_INCREMENT,
  `acompanhamento_id` int NOT NULL,
  `possui_orientador` tinyint NOT NULL DEFAULT '0',
  `nome_orientador` varchar(150) DEFAULT NULL,
  `efetividade_orientador` int DEFAULT NULL,
  `disponibilidade_orientador` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_orientador_acomp` (`acompanhamento_id`),
  CONSTRAINT `fk_orient_acomp` FOREIGN KEY (`acompanhamento_id`) REFERENCES `acompanhamento_projeto` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `acomp_orientador`
--

LOCK TABLES `acomp_orientador` WRITE;
/*!40000 ALTER TABLE `acomp_orientador` DISABLE KEYS */;
/*!40000 ALTER TABLE `acomp_orientador` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `acomp_sprint`
--

DROP TABLE IF EXISTS `acomp_sprint`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `acomp_sprint` (
  `id` int NOT NULL AUTO_INCREMENT,
  `acompanhamento_id` int NOT NULL,
  `pct_story_points` enum('0-20%','21-40%','41-60%','61-80%','81-100%') NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_sprint_acomp` (`acompanhamento_id`),
  CONSTRAINT `fk_sprint_acomp` FOREIGN KEY (`acompanhamento_id`) REFERENCES `acompanhamento_projeto` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `acomp_sprint`
--

LOCK TABLES `acomp_sprint` WRITE;
/*!40000 ALTER TABLE `acomp_sprint` DISABLE KEYS */;
/*!40000 ALTER TABLE `acomp_sprint` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `acompanhamento_projeto`
--

DROP TABLE IF EXISTS `acompanhamento_projeto`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `acompanhamento_projeto` (
  `id` int NOT NULL AUTO_INCREMENT,
  `projeto_externo_id` int NOT NULL,
  `contrato_id` int NOT NULL,
  `data_resposta` date NOT NULL,
  `modelo_gerenciamento` enum('Tradicional','Agil','Hibrido') NOT NULL,
  `pct_conclusao` enum('0-20%','21-40%','41-60%','61-80%','81-100%') NOT NULL,
  `status_cronograma` enum('Dentro do prazo','Com risco de atraso','Atrasado','Concluido') NOT NULL,
  `motivos_atraso` text,
  `capacitacao_equipe` tinyint NOT NULL,
  `eficacia_metodologia` tinyint NOT NULL,
  `nivel_retrabalho` tinyint NOT NULL,
  `comunicacao_cliente` tinyint NOT NULL,
  `suficiencia_orcamento` tinyint DEFAULT NULL,
  `orcamento_nao_necessario` tinyint NOT NULL DEFAULT '0',
  `external_id` varchar(100) DEFAULT NULL,
  `external_source` varchar(50) DEFAULT NULL,
  `primera_resposta` tinyint(1) DEFAULT '0',
  `cliente_percebeu_valor` int DEFAULT NULL,
  `pct_marcos_prazo` varchar(20) DEFAULT NULL,
  `variacao_escopo` int DEFAULT NULL,
  `impacto_cliente` varchar(50) DEFAULT NULL,
  `abertura_cliente` int DEFAULT NULL,
  `satisfacao_cliente` int DEFAULT NULL,
  `suficiencia_orcamento_nota` int DEFAULT NULL,
  `dados_iniciais_adicionados` json DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_acompanhamento_external` (`external_source`,`external_id`),
  KEY `fk_acomp_projeto` (`projeto_externo_id`),
  KEY `fk_acomp_contrato` (`contrato_id`),
  CONSTRAINT `fk_acomp_contrato` FOREIGN KEY (`contrato_id`) REFERENCES `contrato` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_acomp_projeto` FOREIGN KEY (`projeto_externo_id`) REFERENCES `projeto_externo` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `acompanhamento_projeto_chk_1` CHECK ((`capacitacao_equipe` between 1 and 5)),
  CONSTRAINT `acompanhamento_projeto_chk_2` CHECK ((`eficacia_metodologia` between 1 and 5)),
  CONSTRAINT `acompanhamento_projeto_chk_3` CHECK ((`nivel_retrabalho` between 1 and 5)),
  CONSTRAINT `acompanhamento_projeto_chk_4` CHECK ((`comunicacao_cliente` between 1 and 5)),
  CONSTRAINT `acompanhamento_projeto_chk_5` CHECK ((`suficiencia_orcamento` between 1 and 5))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `acompanhamento_projeto`
--

LOCK TABLES `acompanhamento_projeto` WRITE;
/*!40000 ALTER TABLE `acompanhamento_projeto` DISABLE KEYS */;
/*!40000 ALTER TABLE `acompanhamento_projeto` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `cargo`
--

DROP TABLE IF EXISTS `cargo`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `cargo` (
  `id` int NOT NULL AUTO_INCREMENT,
  `nome` varchar(100) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_cargo_nome` (`nome`)
) ENGINE=InnoDB AUTO_INCREMENT=37 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `cargo`
--

LOCK TABLES `cargo` WRITE;
/*!40000 ALTER TABLE `cargo` DISABLE KEYS */;
INSERT INTO `cargo` VALUES (1,'Analista de BI'),(2,'Analista de Cultura e Performance'),(3,'Analista de Dados'),(4,'Analista de Inovação'),(5,'Analista de Marca'),(6,'Analista de Marketing'),(7,'Analista de Operações'),(8,'Analista SETTA'),(9,'Assessora Financeira'),(10,'Consultor de Projetos'),(11,'Consultora de Projetos'),(12,'Coordenador de D&I'),(13,'Coordenador de GN'),(14,'Coordenador de TD'),(15,'Coordenadora de CE'),(16,'Coordenadora de DM'),(17,'Coordenadora de OP'),(18,'Departamento Criativo'),(19,'Diretor de Gestão de Pessoas'),(20,'Diretora de Marketing e Vendas'),(21,'Diretora de Operações'),(22,'Diretora de Projetos'),(23,'Diretora Presidente'),(24,'Equipe de TI'),(25,'Gerente Comercial'),(26,'Gerente de Gestão de Pessoas'),(27,'Gerente de Inovação'),(28,'Gerente de Marca'),(29,'Gerente de Marketing'),(30,'Gerente de Operações'),(31,'Gerente de Projeto'),(32,'Gerente Financeiro'),(33,'Gerente SETTA'),(34,'Membro'),(35,'Negociador'),(36,'PMO');
/*!40000 ALTER TABLE `cargo` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `categoria_transacao`
--

DROP TABLE IF EXISTS `categoria_transacao`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `categoria_transacao` (
  `id` int NOT NULL AUTO_INCREMENT,
  `nome` varchar(100) NOT NULL,
  `tipo` enum('entrada','saida','ambos') NOT NULL,
  `celula_id` int DEFAULT NULL,
  `ativo` tinyint(1) NOT NULL DEFAULT '1',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_categoria_transacao_nome` (`nome`),
  KEY `fk_categoria_celula` (`celula_id`),
  CONSTRAINT `fk_categoria_celula` FOREIGN KEY (`celula_id`) REFERENCES `celula` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='Categorias de receita/despesa';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `categoria_transacao`
--

LOCK TABLES `categoria_transacao` WRITE;
/*!40000 ALTER TABLE `categoria_transacao` DISABLE KEYS */;
/*!40000 ALTER TABLE `categoria_transacao` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `celula`
--

DROP TABLE IF EXISTS `celula`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `celula` (
  `id` int NOT NULL AUTO_INCREMENT,
  `nome` varchar(100) NOT NULL,
  `sigla` varchar(20) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_celula_sigla` (`sigla`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `celula`
--

LOCK TABLES `celula` WRITE;
/*!40000 ALTER TABLE `celula` DISABLE KEYS */;
INSERT INTO `celula` VALUES (1,'Presidência','PRES'),(2,'Marketing e Vendas','MKTV'),(3,'Gestão de Pessoas','GP'),(4,'Projetos','PROJ'),(5,'Operações','OPS');
/*!40000 ALTER TABLE `celula` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `cliente`
--

DROP TABLE IF EXISTS `cliente`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `cliente` (
  `id` int NOT NULL AUTO_INCREMENT,
  `nome` varchar(150) NOT NULL,
  `cpf_cnpj` varchar(20) DEFAULT NULL,
  `email` varchar(150) DEFAULT NULL,
  `telefone` varchar(50) DEFAULT NULL COMMENT 'Telefone principal',
  `external_id` varchar(100) DEFAULT NULL COMMENT 'ID na fonte externa (Pipefy)',
  `external_source` varchar(50) DEFAULT NULL COMMENT 'pipefy_comercial | pipefy_financeiro | manual',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_cliente_cpf_cnpj` (`cpf_cnpj`),
  UNIQUE KEY `uk_cliente_external` (`external_source`,`external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `cliente`
--

LOCK TABLES `cliente` WRITE;
/*!40000 ALTER TABLE `cliente` DISABLE KEYS */;
/*!40000 ALTER TABLE `cliente` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `conta_bancaria`
--

DROP TABLE IF EXISTS `conta_bancaria`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `conta_bancaria` (
  `id` int NOT NULL AUTO_INCREMENT,
  `nome` varchar(100) NOT NULL,
  `tipo` enum('banco','pix','dinheiro','outro') NOT NULL,
  `ativo` tinyint(1) NOT NULL DEFAULT '1',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_conta_bancaria_nome` (`nome`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='Contas bancarias da Meta';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `conta_bancaria`
--

LOCK TABLES `conta_bancaria` WRITE;
/*!40000 ALTER TABLE `conta_bancaria` DISABLE KEYS */;
INSERT INTO `conta_bancaria` VALUES (1,'Cora','banco',1),(2,'Asaas','banco',1),(3,'Santander','banco',1),(4,'Lojinha de GP','dinheiro',1);
/*!40000 ALTER TABLE `conta_bancaria` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `contrato`
--

DROP TABLE IF EXISTS `contrato`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `contrato` (
  `id` int NOT NULL AUTO_INCREMENT,
  `cliente_id` int NOT NULL,
  `projeto_externo_id` int NOT NULL,
  `numero` varchar(50) NOT NULL,
  `valor_total` decimal(15,2) NOT NULL,
  `data_inicio` date DEFAULT NULL,
  `data_fim` date DEFAULT NULL,
  `quantidade_parcelas` int DEFAULT NULL COMMENT 'Total de parcelas (1 = a vista)',
  `forma_pagamento_id` int DEFAULT NULL COMMENT 'FK forma_pagamento',
  `estimativa_gastos_ppp` decimal(15,2) DEFAULT NULL COMMENT 'Custo estimado - base para margem',
  `fase_atual` varchar(100) DEFAULT NULL COMMENT 'Fase no Pipefy Financeiro (Em pagamento, Concluido, etc)',
  `data_vencimento_base` date DEFAULT NULL COMMENT 'Data base para calcular vencimentos das parcelas',
  `data_inicio_pagamento` datetime DEFAULT NULL COMMENT 'Timestamp REAL de quando entrou em "Em pagamento" (Pipefy)',
  `finalizado_em` datetime DEFAULT NULL COMMENT 'Timestamp REAL de conclusao/cancelamento (Pipefy)',
  `external_id` varchar(100) DEFAULT NULL,
  `external_source` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_contrato_numero` (`numero`),
  UNIQUE KEY `uq_contrato_projeto` (`projeto_externo_id`),
  UNIQUE KEY `uk_contrato_external` (`external_source`,`external_id`),
  KEY `fk_contrato_cliente` (`cliente_id`),
  KEY `fk_contrato_forma_pagamento` (`forma_pagamento_id`),
  CONSTRAINT `fk_contrato_cliente` FOREIGN KEY (`cliente_id`) REFERENCES `cliente` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_contrato_forma_pagamento` FOREIGN KEY (`forma_pagamento_id`) REFERENCES `forma_pagamento` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_contrato_projeto` FOREIGN KEY (`projeto_externo_id`) REFERENCES `projeto_externo` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `contrato`
--

LOCK TABLES `contrato` WRITE;
/*!40000 ALTER TABLE `contrato` DISABLE KEYS */;
/*!40000 ALTER TABLE `contrato` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `contrato_pagamento`
--

DROP TABLE IF EXISTS `contrato_pagamento`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `contrato_pagamento` (
  `id` int NOT NULL AUTO_INCREMENT,
  `contrato_id` int NOT NULL,
  `cliente_id` int NOT NULL,
  `projeto_externo_id` int NOT NULL,
  `forma_pagamento_id` int NOT NULL,
  `valor` decimal(15,2) NOT NULL,
  `data_vencimento` date DEFAULT NULL,
  `data_pagamento` date DEFAULT NULL,
  `status` varchar(50) NOT NULL DEFAULT 'pendente',
  `numero_parcela` int NOT NULL DEFAULT '1' COMMENT 'Sequencia da parcela (1, 2, 3...)',
  `total_parcelas` int NOT NULL DEFAULT '1' COMMENT 'Snapshot de contrato.quantidade_parcelas',
  `external_id` varchar(100) DEFAULT NULL,
  `external_source` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_contrato_pagamento_external` (`external_source`,`external_id`),
  KEY `fk_cp_contrato` (`contrato_id`),
  KEY `fk_cp_cliente` (`cliente_id`),
  KEY `fk_cp_projeto` (`projeto_externo_id`),
  KEY `fk_cp_forma` (`forma_pagamento_id`),
  KEY `idx_pgto_vencimento` (`data_vencimento`,`status`),
  CONSTRAINT `fk_cp_cliente` FOREIGN KEY (`cliente_id`) REFERENCES `cliente` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_cp_contrato` FOREIGN KEY (`contrato_id`) REFERENCES `contrato` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_cp_forma` FOREIGN KEY (`forma_pagamento_id`) REFERENCES `forma_pagamento` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_cp_projeto` FOREIGN KEY (`projeto_externo_id`) REFERENCES `projeto_externo` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `contrato_pagamento`
--

LOCK TABLES `contrato_pagamento` WRITE;
/*!40000 ALTER TABLE `contrato_pagamento` DISABLE KEYS */;
/*!40000 ALTER TABLE `contrato_pagamento` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `coordenacao`
--

DROP TABLE IF EXISTS `coordenacao`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `coordenacao` (
  `id` int NOT NULL AUTO_INCREMENT,
  `celula_id` int NOT NULL,
  `nome` varchar(100) NOT NULL,
  `sigla` varchar(10) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_coord_sigla` (`sigla`),
  KEY `fk_coord_celula` (`celula_id`),
  CONSTRAINT `fk_coord_celula` FOREIGN KEY (`celula_id`) REFERENCES `celula` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `coordenacao`
--

LOCK TABLES `coordenacao` WRITE;
/*!40000 ALTER TABLE `coordenacao` DISABLE KEYS */;
INSERT INTO `coordenacao` VALUES (1,4,'Tecnologia e Desenvolvimento','TD'),(2,4,'Gestão de Negócios','GN'),(3,4,'Otimização de Processos','OP'),(4,4,'Desenvolvimento de Máquinas','DM'),(5,4,'Construção e Energia','CE');
/*!40000 ALTER TABLE `coordenacao` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `dim_lead_origem`
--

DROP TABLE IF EXISTS `dim_lead_origem`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dim_lead_origem` (
  `id` int NOT NULL AUTO_INCREMENT,
  `raw_value` varchar(255) NOT NULL COMMENT 'Valor original do Pipefy',
  `canonical_value` varchar(100) DEFAULT NULL COMMENT 'Valor canonico (pos-workshop)',
  `source_field` varchar(100) NOT NULL COMMENT 'start_form | ld',
  `ativo` tinyint(1) NOT NULL DEFAULT '1',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_dim_lead_origem_raw` (`source_field`,`raw_value`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='Origens de lead - taxonomia agnostica (raw + canonical)';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `dim_lead_origem`
--

LOCK TABLES `dim_lead_origem` WRITE;
/*!40000 ALTER TABLE `dim_lead_origem` DISABLE KEYS */;
/*!40000 ALTER TABLE `dim_lead_origem` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `dim_motivo_perda`
--

DROP TABLE IF EXISTS `dim_motivo_perda`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dim_motivo_perda` (
  `id` int NOT NULL AUTO_INCREMENT,
  `raw_value` varchar(255) NOT NULL,
  `canonical_value` varchar(100) DEFAULT NULL,
  `source_field` varchar(100) NOT NULL COMMENT 'Qual dos 6 campos do Pipefy',
  `ativo` tinyint(1) NOT NULL DEFAULT '1',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_dim_motivo_perda_raw` (`source_field`,`raw_value`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='Motivos de perda - taxonomia agnostica (raw + canonical)';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `dim_motivo_perda`
--

LOCK TABLES `dim_motivo_perda` WRITE;
/*!40000 ALTER TABLE `dim_motivo_perda` DISABLE KEYS */;
/*!40000 ALTER TABLE `dim_motivo_perda` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `forma_pagamento`
--

DROP TABLE IF EXISTS `forma_pagamento`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `forma_pagamento` (
  `id` int NOT NULL AUTO_INCREMENT,
  `nome` varchar(100) NOT NULL,
  `descricao` text,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `forma_pagamento`
--

LOCK TABLES `forma_pagamento` WRITE;
/*!40000 ALTER TABLE `forma_pagamento` DISABLE KEYS */;
INSERT INTO `forma_pagamento` VALUES (1,'Boleto',NULL),(2,'PIX',NULL),(3,'Transferência Bancária',NULL),(4,'Cartão de Crédito',NULL);
/*!40000 ALTER TABLE `forma_pagamento` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `leads`
--

DROP TABLE IF EXISTS `leads`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `leads` (
  `id` int NOT NULL AUTO_INCREMENT,
  `nome` varchar(200) NOT NULL,
  `email` varchar(200) DEFAULT NULL,
  `telefone` varchar(50) DEFAULT NULL,
  `empresa` varchar(200) DEFAULT NULL,
  `cargo` varchar(100) DEFAULT NULL,
  `external_id` varchar(100) DEFAULT NULL,
  `external_source` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_lead_external` (`external_source`,`external_id`),
  KEY `idx_lead_email` (`email`),
  KEY `idx_lead_empresa` (`empresa`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='Contato comercial - pode gerar multiplas oportunidades';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `leads`
--

LOCK TABLES `leads` WRITE;
/*!40000 ALTER TABLE `leads` DISABLE KEYS */;
/*!40000 ALTER TABLE `leads` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `membro`
--

DROP TABLE IF EXISTS `membro`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `membro` (
  `id` int NOT NULL AUTO_INCREMENT,
  `nome` varchar(150) NOT NULL,
  `email` varchar(150) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_membro_email` (`email`)
) ENGINE=InnoDB AUTO_INCREMENT=75 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `membro`
--

LOCK TABLES `membro` WRITE;
/*!40000 ALTER TABLE `membro` DISABLE KEYS */;
INSERT INTO `membro` VALUES (1,'Aloysio Felipe Saad Silva','aloysiosaad@metaconsultoria.com'),(2,'Ana Beatriz Lole Augusto dos Santos','analole@metaconsultoria.com'),(3,'Ana Luísa dos Santos Aquino','analuisaaquino@metaconsultoria.com'),(4,'Ana Luísa dos Santos da Silveira da Mata Almeida','ana_almeida@metaconsultoria.com'),(5,'Anallu Pinheiro Guzzo de Souza','analluguzzo@metaconsultoria.com'),(6,'Anna Clara Santos Dias Pimentel','annacpimentel@metaconsultoria.com'),(7,'Anthony Vargas da Silva','Anthony@metaconsultoria.com'),(8,'Antônia Leite Peçanha','antonialpecanha@metaconsultoria.com'),(9,'Beatriz Breitas Santos Silva','beatrizbreitas@metaconsultoria.com'),(10,'Bernardo Chavão Marques','bernardo.chavao@metaconsultoria.com'),(11,'Bernardo Pacheco Nascimento de Queiroz','Bernardoqueiroz@metaconsultoria.com'),(12,'Breno Ferreira Noqui','brenonoqui@metaconsultoria.com'),(13,'Breno Martin Irigoyen Lourival','BrenoLourival@metaconsultoria.com'),(14,'Bryan Vidal Ribeiro Lemos','Bryanvidal@metaconsultoria.com'),(15,'Camille Perazzine de Sá','camille.perazzini@metaconsultoria.com'),(16,'Carol Alves Pinto','carolalves@metaconsultoria.com'),(17,'Carolina Bragança de Oliveira','carolbraganca@metaconsultoria.com'),(18,'Carolina Torii Britto','caroltoriibritto@metaconsultoria.com'),(19,'Cauã Coelho Cintra Martins','martinscaua@metaconsultoria.com'),(20,'Daniel Teitelroit Penna','Danieltpenna@metaconsultoria.com'),(21,'Davi Moreno de Oliveira','davi_moreno@metaconsultoria.com'),(22,'Denise Moura Mendes','denise_moura@metaconsultoria.com'),(23,'Diana Passini Rangel Castelo Branco','dianapassini@metaconsultoria.com'),(24,'Felipe Cabral Liporage','fcliporage@metaconsultoria.com'),(25,'Felipe Souto Castro','felipesouto@metaconsultoria.com'),(26,'Filipe Moreira Sampaio Barros','setta@metaconsultoria.com'),(27,'Filipe Pinto da Silva','filipe.pinto@metaconsultoria.com'),(28,'Gabriel Amaral Rodrigues da Silva','amaralg@metaconsultoria.com'),(29,'Gabriel Nunes de Oliveira','gabrielnunes@metaconsultoria.com'),(30,'Giovana Drummond Pasqualino','Gio_Drummond@metaconsultoria.com'),(31,'Giovana Teófilo de Aguiar','giovanaaguiar@metaconsultoria.com'),(32,'Gustavo Alves Duarte Ferreira','gustavoferreira@metaconsultoria.com'),(33,'Gustavo Sardella Alvim','gustavoalvim@metaconsultoria.com'),(34,'Henrique Almeida Trope','htrope@metaconsultoria.com'),(35,'Iago Lessa Guindani','iago_lessa@metaconsultoria.com'),(36,'João Guilherme Cabral Mendes','Joao.mendes@metaconsultoria.com'),(37,'João Pedro Costa','joaopedrox@metaconsultoria.com'),(38,'João Vitor Dias Moreira','joaodias@metaconsultoria.com'),(39,'Jorge Heitor de Oliveira Matheus','heitormatheoliv@metaconsultoria.com'),(40,'Julia Henrique De Amorim Nunes','julianunes@metaconsultoria.com'),(41,'Julia Peixoto Dib','juliadib@metaconsultoria.com'),(42,'Juliana Rodrigues de Souza','julianarodrigues@metaconsultoria.com'),(43,'Julie Victoria Vasconcelos Brandão','v_brandao@metaconsultoria.com'),(44,'Leonardo Salles Cypriano dos Santos','leonardocypriano@metaconsultoria.com'),(45,'Letícia Cavalcanti de Campos Queiroz','leticiaqueiroz@metaconsultoria.com'),(46,'Letícia Racca Cleto da Silva','leticiaracca@metaconsultoria.com'),(47,'Luana Santos Teixeira Ferreira','luana_ferreira@metaconsultoria.com'),(48,'Lucas Vaz Malheiro','lucasvazmalheiro@metaconsultoria.com'),(49,'Lucas Vieira Alves','Lucas.vieira@metaconsultoria.com'),(50,'Lucianna Peixoto dos Santos Poncione','luciannaponcione@metaconsultoria.com'),(51,'Luís Filipe Araújo França Silva','luis_araujo@metaconsultoria.com'),(52,'Luísa Ruch Werneck Fonseca','luisarwerneck@metaconsultoria.com'),(53,'Luíza Botelho Ferreira','luizabotelho@metaconsultoria.com'),(54,'Marcelo Benevides Silva Filho','marcelob@metaconsultoria.com'),(55,'Marco Antônio Simas Pereira','marcosimas@metaconsultoria.com'),(56,'Marcos Vinícius Alves Pereira','marcosvinicius@metaconsultoria.com'),(57,'Maria Eduarda Oliveira Gomes','maria.ogomes@metaconsultoria.com'),(58,'Maria Luiza Mendonça de Oliveira Gonçalves','maluiza@metaconsultoria.com'),(59,'Mariana Pereira de Almeida','marianapereira@metaconsultoria.com'),(60,'Marina Ferreira da Costa','marinadacosta@metaconsultoria.com'),(61,'Mateus Titoneli Guedes','mateustitoneli@metaconsultoria.com'),(62,'Naylan Cardoso Nogueira','naylan@metaconsultoria.com'),(63,'Paula Márcia Soares Monteiro','paulas@metaconsultoria.com'),(64,'Pedro Henrique Alves dos Santos','pedrohsantos@metaconsultoria.com'),(65,'Pedro Henrique Marchesano Campos','phcampos@metaconsultoria.com'),(66,'Pedro José Veiga Schubnell','pedroveiga@metaconsultoria.com'),(67,'Rayssa Mattos Maues','rayssamattos@metaconsultoria.com'),(68,'Reinaldo Oliveira Pinto','reinaldo_op@metaconsultoria.com'),(69,'Samuel de Lima Rangel','Samuelrangel@metaconsultoria.com'),(70,'Sávio Vargas Magalhães','saviovargas@metaconsultoria.com'),(71,'Sofia Silva Ganim Vasconcellos','sofiaganim@metaconsultoria.com'),(72,'Vinícius Luzo Sousa Neves','viniciusluzo@metaconsultoria.com'),(73,'Yan Porto Pereira Franco','yanporto@metaconsultoria.com'),(74,'Yan Souto Novaes Souza','yanovaes@metaconsultoria.com');
/*!40000 ALTER TABLE `membro` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `membro_cargo`
--

DROP TABLE IF EXISTS `membro_cargo`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `membro_cargo` (
  `id` int NOT NULL AUTO_INCREMENT,
  `membro_id` int NOT NULL,
  `cargo_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_membro_cargo` (`membro_id`,`cargo_id`),
  KEY `fk_membro_cargo_cargo` (`cargo_id`),
  CONSTRAINT `fk_membro_cargo_cargo` FOREIGN KEY (`cargo_id`) REFERENCES `cargo` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_membro_cargo_membro` FOREIGN KEY (`membro_id`) REFERENCES `membro` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=128 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `membro_cargo`
--

LOCK TABLES `membro_cargo` WRITE;
/*!40000 ALTER TABLE `membro_cargo` DISABLE KEYS */;
INSERT INTO `membro_cargo` VALUES (1,1,4),(2,1,10),(3,2,11),(4,2,24),(5,3,30),(6,4,11),(7,5,11),(8,6,1),(9,6,11),(10,6,24),(11,7,10),(12,8,9),(13,8,11),(15,9,11),(16,9,18),(14,9,31),(18,10,18),(17,10,32),(19,11,35),(20,12,34),(21,13,35),(22,14,19),(23,15,11),(24,16,5),(25,16,11),(26,17,2),(27,17,11),(28,17,18),(30,18,11),(29,18,31),(31,19,10),(32,20,10),(33,21,7),(34,21,10),(35,22,33),(37,23,11),(36,23,31),(38,24,10),(39,24,24),(40,25,10),(41,26,8),(42,26,10),(43,27,10),(44,27,24),(45,28,10),(46,29,34),(47,30,20),(48,31,11),(49,31,18),(51,32,10),(50,32,28),(52,33,35),(53,34,33),(54,35,4),(55,35,10),(56,35,18),(57,36,10),(58,37,10),(59,38,10),(62,39,10),(61,39,12),(60,39,26),(63,40,17),(64,41,36),(65,42,9),(66,42,11),(67,42,18),(68,43,16),(69,44,27),(70,45,11),(72,46,11),(71,46,31),(74,47,11),(73,47,31),(75,48,10),(76,48,18),(77,49,4),(78,49,10),(79,50,22),(81,51,10),(80,51,33),(82,52,21),(83,53,29),(84,54,35),(85,55,10),(86,56,10),(87,57,6),(88,57,11),(89,58,11),(90,59,11),(91,60,23),(92,61,3),(93,61,10),(94,61,24),(95,62,4),(96,63,15),(97,63,24),(98,64,4),(99,64,10),(101,65,10),(100,65,13),(102,66,4),(103,66,10),(104,67,11),(105,68,10),(106,69,8),(107,69,10),(108,70,10),(109,70,18),(110,71,2),(111,71,11),(114,72,18),(112,72,25),(113,72,35),(115,73,10),(116,74,14);
/*!40000 ALTER TABLE `membro_cargo` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `membro_celula`
--

DROP TABLE IF EXISTS `membro_celula`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `membro_celula` (
  `id` int NOT NULL AUTO_INCREMENT,
  `membro_id` int NOT NULL,
  `celula_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_membro_celula` (`membro_id`,`celula_id`),
  KEY `fk_mc_celula` (`celula_id`),
  CONSTRAINT `fk_mc_celula` FOREIGN KEY (`celula_id`) REFERENCES `celula` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_mc_membro` FOREIGN KEY (`membro_id`) REFERENCES `membro` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=128 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `membro_celula`
--

LOCK TABLES `membro_celula` WRITE;
/*!40000 ALTER TABLE `membro_celula` DISABLE KEYS */;
INSERT INTO `membro_celula` VALUES (1,1,4),(2,2,4),(3,3,5),(4,4,4),(5,5,4),(6,6,2),(7,7,4),(8,8,5),(9,9,4),(10,10,5),(11,11,2),(12,12,4),(13,13,2),(14,14,3),(15,15,4),(16,16,2),(17,17,3),(18,18,4),(19,19,4),(20,20,4),(22,21,4),(21,21,5),(23,22,3),(24,23,4),(25,24,4),(26,25,4),(27,26,3),(28,27,4),(29,28,4),(30,29,4),(31,30,2),(32,31,2),(33,32,2),(34,33,2),(35,34,3),(36,35,4),(37,36,4),(38,37,4),(39,38,4),(40,39,3),(41,40,4),(42,41,4),(43,42,5),(44,43,4),(45,44,4),(46,45,4),(47,46,4),(48,47,4),(49,48,4),(50,49,4),(51,50,4),(52,51,3),(53,52,5),(54,53,2),(55,54,2),(56,55,4),(57,56,4),(58,57,2),(59,58,4),(60,59,4),(61,60,1),(62,61,3),(63,62,4),(64,63,4),(65,64,4),(66,65,4),(67,66,4),(68,67,4),(69,68,4),(70,69,3),(71,70,4),(72,71,3),(73,72,2),(74,73,4),(75,74,4);
/*!40000 ALTER TABLE `membro_celula` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `membro_coordenacao`
--

DROP TABLE IF EXISTS `membro_coordenacao`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `membro_coordenacao` (
  `id` int NOT NULL AUTO_INCREMENT,
  `membro_id` int NOT NULL,
  `coordenacao_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_membro_coordenacao` (`membro_id`,`coordenacao_id`),
  KEY `fk_mcoord_coord` (`coordenacao_id`),
  CONSTRAINT `fk_mcoord_coord` FOREIGN KEY (`coordenacao_id`) REFERENCES `coordenacao` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_mcoord_membro` FOREIGN KEY (`membro_id`) REFERENCES `membro` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=64 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `membro_coordenacao`
--

LOCK TABLES `membro_coordenacao` WRITE;
/*!40000 ALTER TABLE `membro_coordenacao` DISABLE KEYS */;
INSERT INTO `membro_coordenacao` VALUES (1,1,1),(2,2,5),(3,4,5),(5,5,3),(4,5,5),(6,7,5),(7,8,3),(8,9,3),(9,15,1),(10,16,2),(11,16,3),(12,17,3),(13,18,3),(14,19,4),(15,20,4),(17,21,1),(16,21,2),(18,21,3),(19,23,3),(20,24,1),(21,25,4),(22,26,1),(23,27,1),(24,28,5),(25,31,2),(26,32,4),(27,35,2),(28,35,4),(29,36,3),(31,37,1),(30,37,2),(32,38,5),(33,39,3),(34,40,3),(35,42,3),(36,43,4),(37,45,2),(38,46,3),(39,47,3),(40,48,3),(41,49,4),(42,51,5),(43,55,5),(44,56,4),(45,57,5),(46,58,5),(47,59,5),(48,61,5),(49,63,5),(50,64,2),(51,64,3),(52,65,2),(53,66,3),(54,67,2),(55,67,3),(56,68,4),(57,69,1),(58,70,4),(59,71,3),(60,73,3),(61,74,1);
/*!40000 ALTER TABLE `membro_coordenacao` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `membro_projeto`
--

DROP TABLE IF EXISTS `membro_projeto`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `membro_projeto` (
  `id` int NOT NULL AUTO_INCREMENT,
  `membro_id` int NOT NULL,
  `projeto_externo_id` int NOT NULL,
  `coordenacao_id` int NOT NULL,
  `cargo_id` int NOT NULL,
  `data_entrada` date DEFAULT NULL,
  `data_saida` date DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_mp_membro` (`membro_id`),
  KEY `fk_mp_projeto` (`projeto_externo_id`),
  KEY `fk_mp_coord` (`coordenacao_id`),
  KEY `fk_mp_cargo` (`cargo_id`),
  CONSTRAINT `fk_mp_cargo` FOREIGN KEY (`cargo_id`) REFERENCES `cargo` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_mp_coord` FOREIGN KEY (`coordenacao_id`) REFERENCES `coordenacao` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_mp_membro` FOREIGN KEY (`membro_id`) REFERENCES `membro` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_mp_projeto` FOREIGN KEY (`projeto_externo_id`) REFERENCES `projeto_externo` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=127 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `membro_projeto`
--

LOCK TABLES `membro_projeto` WRITE;
/*!40000 ALTER TABLE `membro_projeto` DISABLE KEYS */;
INSERT INTO `membro_projeto` VALUES (64,2,27,5,11,NULL,NULL),(65,2,19,5,11,NULL,NULL),(66,3,29,2,31,NULL,NULL),(67,4,21,5,11,NULL,NULL),(68,7,27,5,10,NULL,NULL),(69,8,26,3,11,NULL,NULL),(70,9,20,4,31,NULL,NULL),(71,10,26,2,10,NULL,NULL),(72,11,18,2,10,NULL,NULL),(73,12,26,3,10,NULL,NULL),(74,16,17,2,11,NULL,NULL),(75,17,22,3,11,NULL,NULL),(76,18,23,5,31,NULL,NULL),(77,18,22,3,31,NULL,NULL),(78,19,25,4,10,NULL,NULL),(79,20,20,4,10,NULL,NULL),(80,21,22,3,10,NULL,NULL),(81,23,21,5,31,NULL,NULL),(82,23,17,2,31,NULL,NULL),(83,24,25,4,10,NULL,NULL),(84,35,25,4,10,NULL,NULL),(85,35,16,2,10,NULL,NULL),(86,36,22,3,10,NULL,NULL),(87,37,17,2,10,NULL,NULL),(88,38,23,5,10,NULL,NULL),(89,39,28,3,10,NULL,NULL),(90,41,29,2,31,NULL,NULL),(91,41,27,5,31,NULL,NULL),(92,41,19,5,31,NULL,NULL),(93,45,17,2,11,NULL,NULL),(94,46,26,3,31,NULL,NULL),(95,46,26,2,31,NULL,NULL),(96,47,25,4,31,NULL,NULL),(97,47,24,5,31,NULL,NULL),(98,47,18,2,31,NULL,NULL),(99,48,25,4,10,NULL,NULL),(100,48,22,3,10,NULL,NULL),(101,49,20,4,10,NULL,NULL),(102,50,28,3,31,NULL,NULL),(103,55,27,5,10,NULL,NULL),(104,57,27,5,11,NULL,NULL),(105,57,19,5,11,NULL,NULL),(106,58,24,5,11,NULL,NULL),(107,58,23,5,11,NULL,NULL),(108,59,21,5,11,NULL,NULL),(109,62,16,2,31,NULL,NULL),(110,64,22,3,10,NULL,NULL),(111,64,16,2,10,NULL,NULL),(112,66,26,3,10,NULL,NULL),(113,67,22,3,11,NULL,NULL),(114,68,26,2,10,NULL,NULL),(115,68,25,4,10,NULL,NULL),(116,71,26,3,11,NULL,NULL);
/*!40000 ALTER TABLE `membro_projeto` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `oportunidade`
--

DROP TABLE IF EXISTS `oportunidade`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `oportunidade` (
  `id` int NOT NULL AUTO_INCREMENT,
  `lead_id` int DEFAULT NULL,
  `cliente_id` int DEFAULT NULL COMMENT 'Preenchido quando vira contrato',
  `fase_atual_nome` varchar(100) NOT NULL COMMENT 'Snapshot do nome (denormalizacao para queries simples)',
  `fase_atual_id` varchar(50) NOT NULL COMMENT 'ID da fase no Pipefy',
  `responsaveis` varchar(500) DEFAULT NULL COMMENT 'Negociador(es) - analise de performance',
  `valor_fechado` decimal(15,2) DEFAULT NULL COMMENT 'Valor canonico (Pre-Assinatura)',
  `origem_id` int DEFAULT NULL,
  `motivo_perda_id` int DEFAULT NULL,
  `coordenacao_id` int DEFAULT NULL COMMENT 'Extraido da etiqueta do card',
  `status_terminal` enum('ativo','fechado','desistido','recusado','postergado') NOT NULL DEFAULT 'ativo',
  `criado_em` datetime NOT NULL,
  `finalizado_em` datetime DEFAULT NULL,
  `external_id` varchar(100) NOT NULL,
  `external_source` varchar(50) NOT NULL DEFAULT 'pipefy_comercial',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_oportunidade_external` (`external_source`,`external_id`),
  KEY `fk_oportunidade_lead` (`lead_id`),
  KEY `fk_oportunidade_cliente` (`cliente_id`),
  KEY `fk_oportunidade_origem` (`origem_id`),
  KEY `fk_oportunidade_motivo_perda` (`motivo_perda_id`),
  KEY `fk_oportunidade_coordenacao` (`coordenacao_id`),
  KEY `idx_oportunidade_fase` (`fase_atual_id`),
  KEY `idx_oportunidade_criado` (`criado_em`),
  KEY `idx_oportunidade_status` (`status_terminal`),
  KEY `idx_oportunidade_finalizado` (`finalizado_em`),
  CONSTRAINT `fk_oportunidade_cliente` FOREIGN KEY (`cliente_id`) REFERENCES `cliente` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_oportunidade_coordenacao` FOREIGN KEY (`coordenacao_id`) REFERENCES `coordenacao` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_oportunidade_lead` FOREIGN KEY (`lead_id`) REFERENCES `leads` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_oportunidade_motivo_perda` FOREIGN KEY (`motivo_perda_id`) REFERENCES `dim_motivo_perda` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_oportunidade_origem` FOREIGN KEY (`origem_id`) REFERENCES `dim_lead_origem` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='Card do Pipefy Comercial - estado atual';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `oportunidade`
--

LOCK TABLES `oportunidade` WRITE;
/*!40000 ALTER TABLE `oportunidade` DISABLE KEYS */;
/*!40000 ALTER TABLE `oportunidade` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `oportunidade_phase_history`
--

DROP TABLE IF EXISTS `oportunidade_phase_history`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `oportunidade_phase_history` (
  `id` int NOT NULL AUTO_INCREMENT,
  `oportunidade_id` int NOT NULL,
  `from_phase_id` varchar(50) DEFAULT NULL COMMENT 'NULL na criacao do card',
  `from_phase_nome` varchar(100) DEFAULT NULL,
  `to_phase_id` varchar(50) NOT NULL,
  `to_phase_nome` varchar(100) NOT NULL,
  `moved_at` datetime NOT NULL,
  `moved_by` varchar(200) DEFAULT NULL,
  `duration_previous_phase_seconds` bigint DEFAULT NULL COMMENT 'Calculado pelo n8n na ingestao',
  `external_event_id` varchar(100) DEFAULT NULL,
  `external_source` varchar(50) NOT NULL DEFAULT 'pipefy_webhook',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_oport_phase_event` (`external_source`,`external_event_id`),
  KEY `idx_oport_phase_oport_moved` (`oportunidade_id`,`moved_at`),
  KEY `idx_oport_phase_to_moved` (`to_phase_id`,`moved_at`),
  CONSTRAINT `fk_oport_phase_oportunidade` FOREIGN KEY (`oportunidade_id`) REFERENCES `oportunidade` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='Historico de mudancas de fase (append-only)';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `oportunidade_phase_history`
--

LOCK TABLES `oportunidade_phase_history` WRITE;
/*!40000 ALTER TABLE `oportunidade_phase_history` DISABLE KEYS */;
/*!40000 ALTER TABLE `oportunidade_phase_history` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `projeto_externo`
--

DROP TABLE IF EXISTS `projeto_externo`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `projeto_externo` (
  `id` int NOT NULL AUTO_INCREMENT,
  `nome` varchar(150) NOT NULL,
  `descricao` text,
  `data_inicio` date DEFAULT NULL,
  `possui_orientador` tinyint(1) DEFAULT NULL COMMENT 'NULL = nao informado, 0 = nao possui, 1 = possui',
  `nome_orientador` varchar(150) DEFAULT NULL,
  `external_id` varchar(100) DEFAULT NULL,
  `external_source` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_projeto_externo_external` (`external_source`,`external_id`)
) ENGINE=InnoDB AUTO_INCREMENT=31 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `projeto_externo`
--

LOCK TABLES `projeto_externo` WRITE;
/*!40000 ALTER TABLE `projeto_externo` DISABLE KEYS */;
INSERT INTO `projeto_externo` VALUES (16,'AM do Amor','Projeto externo importado do portifolio de 05/05/2026. Prazo oficial: 13/03/2026. Status no portifolio: Atrasado.',NULL,NULL,NULL,'portfolio-2026-05-05-am-do-amor','portfolio_projetos_externos_2026_05_05'),(17,'Analisa Bebidas Gratis','Projeto externo importado do portifolio de 05/05/2026. Prazo oficial: 21/07/2026. Status no portifolio: Pausado.',NULL,NULL,NULL,'portfolio-2026-05-05-analisa-bebidas-gratis','portfolio_projetos_externos_2026_05_05'),(18,'Analisa Michael Douglas','Projeto externo importado do portifolio de 05/05/2026. Prazo oficial: 27/07/2026. Status no portifolio: No prazo.',NULL,NULL,NULL,'portfolio-2026-05-05-analisa-michael-douglas','portfolio_projetos_externos_2026_05_05'),(19,'Arquiteta Odonto','Projeto externo importado do portifolio de 05/05/2026. Prazo oficial: 20/08/2025. Status no portifolio: Atrasado.',NULL,NULL,NULL,'portfolio-2026-05-05-arquiteta-odonto','portfolio_projetos_externos_2026_05_05'),(20,'BN Cinderela 2.0','Projeto externo importado do portifolio de 05/05/2026. Prazo oficial: 15/06/2026. Status no portifolio: No prazo.',NULL,NULL,NULL,'portfolio-2026-05-05-bn-cinderela-2-0','portfolio_projetos_externos_2026_05_05'),(21,'Decora Odonto','Projeto externo importado do portifolio de 05/05/2026. Prazo oficial: 17/04/2026. Status no portifolio: Pausado.',NULL,NULL,NULL,'portfolio-2026-05-05-decora-odonto','portfolio_projetos_externos_2026_05_05'),(22,'Fêmea no Mar','Projeto externo importado do portifolio de 05/05/2026. Prazo oficial: 12/05/2026. Status no portifolio: No prazo.',NULL,NULL,NULL,'portfolio-2026-05-05-femea-no-mar','portfolio_projetos_externos_2026_05_05'),(23,'Legaliza Coelhinha','Projeto externo importado do portifolio de 05/05/2026. Prazo oficial: 02/06/2026. Status no portifolio: No prazo.',NULL,NULL,NULL,'portfolio-2026-05-05-legaliza-coelhinha','portfolio_projetos_externos_2026_05_05'),(24,'Maricônico','Projeto externo importado do portifolio de 05/05/2026. Prazo oficial: 12/05/2026. Status no portifolio: No prazo.',NULL,NULL,NULL,'portfolio-2026-05-05-mariconico','portfolio_projetos_externos_2026_05_05'),(25,'Monitora Petrogarra','Projeto externo importado do portifolio de 05/05/2026. Prazo oficial: 18/08/2026. Status no portifolio: No prazo.',NULL,NULL,NULL,'portfolio-2026-05-05-monitora-petrogarra','portfolio_projetos_externos_2026_05_05'),(26,'Ocean Map','Projeto externo importado do portifolio de 05/05/2026. Prazo oficial: 05/05/2026. Status no portifolio: No prazo.',NULL,NULL,NULL,'portfolio-2026-05-05-ocean-map','portfolio_projetos_externos_2026_05_05'),(27,'Projeta Urgente','Projeto externo importado do portifolio de 05/05/2026. Prazo oficial: 15/11/2025. Status no portifolio: Atrasado.',NULL,NULL,NULL,'portfolio-2026-05-05-projeta-urgente','portfolio_projetos_externos_2026_05_05'),(28,'Quanta','Projeto externo importado do portifolio de 05/05/2026. Prazo oficial: 15/01/2026. Status no portifolio: Atrasado.',NULL,NULL,NULL,'portfolio-2026-05-05-quanta','portfolio_projetos_externos_2026_05_05'),(29,'Valida Bruninho','Projeto externo importado do portifolio de 05/05/2026. Prazo oficial: 20/03/2026. Status no portifolio: Atrasado.',NULL,NULL,NULL,'portfolio-2026-05-05-valida-bruninho','portfolio_projetos_externos_2026_05_05');
/*!40000 ALTER TABLE `projeto_externo` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `projeto_servico`
--

DROP TABLE IF EXISTS `projeto_servico`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `projeto_servico` (
  `id` int NOT NULL AUTO_INCREMENT,
  `projeto_externo_id` int NOT NULL,
  `servico_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_projeto_servico` (`projeto_externo_id`,`servico_id`),
  KEY `fk_ps_servico` (`servico_id`),
  CONSTRAINT `fk_ps_projeto` FOREIGN KEY (`projeto_externo_id`) REFERENCES `projeto_externo` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_ps_servico` FOREIGN KEY (`servico_id`) REFERENCES `servico` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `projeto_servico`
--

LOCK TABLES `projeto_servico` WRITE;
/*!40000 ALTER TABLE `projeto_servico` DISABLE KEYS */;
/*!40000 ALTER TABLE `projeto_servico` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `servico`
--

DROP TABLE IF EXISTS `servico`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `servico` (
  `id` int NOT NULL AUTO_INCREMENT,
  `coordenacao_id` int NOT NULL,
  `nome` varchar(100) NOT NULL,
  `sigla` varchar(10) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_servico_sigla` (`sigla`),
  KEY `fk_servico_coord` (`coordenacao_id`),
  CONSTRAINT `fk_servico_coord` FOREIGN KEY (`coordenacao_id`) REFERENCES `coordenacao` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=28 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `servico`
--

LOCK TABLES `servico` WRITE;
/*!40000 ALTER TABLE `servico` DISABLE KEYS */;
INSERT INTO `servico` VALUES (1,1,'Automação de Processos','APR'),(2,1,'Desenvolvimento de Sites','DVS'),(3,1,'Desenvolvimento de Aplicativos','DVA'),(4,2,'Análise de Mercado','ANM'),(5,2,'Estudo de Viabilidade Econômica','EVE'),(6,2,'Planejamento Estratégico','PLE'),(7,2,'Precificação','PRC'),(8,2,'Financial Planning & Analysis','FPA'),(9,2,'Posicionamento de Marca','PSM'),(10,3,'Estudo de Tempos','EST'),(11,3,'Estruturação Interna','ESI'),(12,3,'Mapeamento de Processos','MPR'),(13,3,'Pesquisa de Clima Operacional','PCO'),(14,3,'Gestão de Estoque','GES'),(15,3,'Simulação de Processos','SPR'),(16,4,'Desenho Mecânico','DSM'),(17,4,'Estudo de Materiais','ESM'),(18,4,'Prototipagem 3D','P3D'),(19,4,'Análise Estrutural','ANE'),(20,5,'Projeto Arquitetônico','PAR'),(21,5,'Vista Humanizada','VST'),(22,5,'Instalações Hidrossanitárias','ISH'),(23,5,'Autovistoria Predial','AVP'),(24,5,'Regularização de Imóveis','RDI'),(25,5,'Orçamento de Obras','ODO'),(26,5,'Instalações Elétricas','ISE'),(27,5,'Estudo de Luminotécnica','ESL');
/*!40000 ALTER TABLE `servico` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `transacao`
--

DROP TABLE IF EXISTS `transacao`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `transacao` (
  `id` int NOT NULL AUTO_INCREMENT,
  `data` date NOT NULL,
  `conta_id` int NOT NULL,
  `tipo` enum('entrada','saida') NOT NULL,
  `categoria_id` int DEFAULT NULL,
  `celula_id` int DEFAULT NULL COMMENT 'Setor da planilha (qual celula movimentou)',
  `valor` decimal(15,2) NOT NULL COMMENT 'Sempre positivo',
  `projeto_externo_id` int DEFAULT NULL COMMENT 'NULL para despesas/receitas operacionais',
  `contrato_pagamento_id` int DEFAULT NULL COMMENT 'NULL exceto quando confirma pagamento de parcela',
  `external_id` varchar(100) NOT NULL,
  `external_source` varchar(50) NOT NULL DEFAULT 'sharepoint_caixa',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_transacao_external` (`external_source`,`external_id`),
  KEY `fk_transacao_categoria` (`categoria_id`),
  KEY `fk_transacao_projeto` (`projeto_externo_id`),
  KEY `fk_transacao_pagamento` (`contrato_pagamento_id`),
  KEY `idx_transacao_data` (`data`),
  KEY `idx_transacao_conta_data` (`conta_id`,`data`),
  KEY `idx_transacao_celula_data` (`celula_id`,`data`),
  CONSTRAINT `fk_transacao_categoria` FOREIGN KEY (`categoria_id`) REFERENCES `categoria_transacao` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_transacao_celula` FOREIGN KEY (`celula_id`) REFERENCES `celula` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_transacao_conta` FOREIGN KEY (`conta_id`) REFERENCES `conta_bancaria` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_transacao_pagamento` FOREIGN KEY (`contrato_pagamento_id`) REFERENCES `contrato_pagamento` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_transacao_projeto` FOREIGN KEY (`projeto_externo_id`) REFERENCES `projeto_externo` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='Transacoes da planilha SharePoint (caixa livre)';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `transacao`
--

LOCK TABLES `transacao` WRITE;
/*!40000 ALTER TABLE `transacao` DISABLE KEYS */;
/*!40000 ALTER TABLE `transacao` ENABLE KEYS */;
UNLOCK TABLES;
SET @@SESSION.SQL_LOG_BIN = @MYSQLDUMP_TEMP_LOG_BIN;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-05-27 15:09:24
